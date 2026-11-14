"""Read-only, root-bound product views over exactly verified capsule bytes.

Raw requests, responses and carrier values never enter summary endpoints. The
bounded replay operation restores covered checkpoints in a temporary directory;
it never runs code from the capsule or falls through to a live dependency.
"""

import io
import json
import re
import tempfile
import zipfile
from collections.abc import Iterator
from functools import cached_property
from pathlib import Path
from typing import Any

from sentinel_replay.boundary import BoundarySession
from sentinel_replay.canonical import event_digest, load_json_unique
from sentinel_replay.capsule import import_capsule_bytes, verify_capsule_bytes
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.provenance import build_provenance
from sentinel_replay.timeline import compress_timeline
from sentinel_replay.workspace_snapshot import (
    WorkspaceManifest,
    restore_workspace,
    verify_workspace,
)

_LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,100}\Z")


def _label(value: object) -> str:
    return value if isinstance(value, str) and _LABEL.fullmatch(value) else "redacted"


class CapsuleInvestigation:
    def __init__(self, data: bytes) -> None:
        self.verified = verify_capsule_bytes(data)
        self.data = data
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.journal = archive.read("journal.jsonl")
            self.artifacts = {
                name.removeprefix("artifacts/"): archive.read(name)
                for name in archive.namelist()
                if name.startswith("artifacts/")
            }
        self.events: list[dict[str, Any]] = []
        for line in self.journal.splitlines():
            event = load_json_unique(line.decode())["event"]
            if not isinstance(event, dict):
                raise ValueError("investigation requires object events")
            self.events.append(event)
        self.summary()  # Reject malformed report artifacts inside the loader boundary.

    def _root(self, expected: str | None) -> None:
        if expected is not None and expected != self.verified.root:
            raise ValueError("pagination root differs from the stored run")

    def _safe_event(self, index: int) -> dict[str, Any]:
        event = self.events[index]
        evidence = event.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {}
        return {
            "step": index,
            "call_id": _label(event.get("call_id")),
            "kind": _label(event.get("kind")),
            "operation": _label(evidence.get("operation")),
            "coverage": _label(evidence.get("coverage", "declared_metadata")),
            "sensitivity": evidence.get("sensitivity")
            if evidence.get("sensitivity") in ("public", "secret")
            else "unspecified",
            "request_digest": event.get("request_digest")
            if isinstance(event.get("request_digest"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", event["request_digest"])
            else None,
        }

    def summary(self) -> dict[str, Any]:
        raw = self.artifacts.get("report.json")
        report = load_json_unique(raw.decode()) if raw else {}
        mode = (
            report.get("mode", "AGENT_OBSERVATION_ONLY") if isinstance(report, dict) else "unknown"
        )
        if not isinstance(mode, str) or mode not in {"EXPLORATORY_BRANCH", "DETERMINISTIC_SIMULATION", "VERIFIED_REPLAY"}:
            mode = "AGENT_OBSERVATION_ONLY"
        # Never promote a supplied report's own VERIFIED_REPLAY claim.
        if mode == "VERIFIED_REPLAY":
            mode = "UNVERIFIED_MODE_CLAIM"
        effects = report.get("independent_effects", {}) if isinstance(report, dict) else {}
        return {
            "run_id": self.verified.run_id,
            "record_type": ("environment_pack" if "pack-definition.json" in self.artifacts else "experiment" if "comparison.json" in self.artifacts else "branch"),
            "journal_root": self.verified.root,
            "records": self.verified.records,
            "artifacts": self.verified.artifacts,
            "mode": mode,
            "terminal_status": report.get("status", "not_reported")
            if isinstance(report, dict) and report.get("status") in ("completed", "unknown")
            else "not_reported",
            "outcomes": {
                "legitimate_task_completed": effects.get("legitimate_task_completed")
                if type(effects.get("legitimate_task_completed")) is bool
                else None,
                "protected_output_count": len(effects["protected_outputs"])
                if isinstance(effects.get("protected_outputs"), list)
                else None,
            }
            if isinstance(effects, dict)
            else {},
            "integrity": "verified_capsule_bytes",
            "replay_coverage": "recorded_boundaries_only",
            "limitation": "Recorder declarations are not independent causal or author evidence.",
        }

    def timeline(
        self, *, offset: int = 0, limit: int = 100, expected_root: str | None = None
    ) -> dict[str, Any]:
        self._root(expected_root)
        if not 0 <= offset <= len(self.events) or not 1 <= limit <= 500:
            raise ValueError("invalid timeline pagination")
        stop = min(offset + limit, len(self.events))
        return {
            "journal_root": self.verified.root,
            "total": len(self.events),
            "offset": offset,
            "next_offset": stop if stop < len(self.events) else None,
            "events": [self._safe_event(index) for index in range(offset, stop)],
        }

    def phases(self) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="sentinel-phases-") as directory:
            journal = Path(directory) / "journal.jsonl"
            journal.write_bytes(self.journal)
            return compress_timeline(journal).to_dict()

    def incidents(self) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        sources: dict[str, int] = {}
        for index, event in enumerate(self.events):
            evidence = event.get("evidence", {})
            if not isinstance(evidence, dict):
                continue
            carrier = evidence.get("carrier")
            if (
                isinstance(carrier, str)
                and evidence.get("carrier_role") == "source"
                and evidence.get("sensitivity") == "secret"
            ):
                sources[carrier] = index
            if (
                isinstance(carrier, str)
                and evidence.get("carrier_role") == "sink"
                and carrier in sources
            ):
                findings.append(
                    {
                        "incident_id": f"{self.verified.run_id}:{index}",
                        "rule_id": "declared_protected_materialization_v1",
                        "root_step": sources[carrier],
                        "step": index,
                        "severity": "high",
                        "basis": "declared secret source and materialized sink share a carrier",
                    }
                )
        return {
            "journal_root": self.verified.root,
            "mode": "DECLARED_EVIDENCE_CLASSIFICATION",
            "incidents": findings,
            "limitation": "A rule miss does not establish absence of an incident.",
        }

    @cached_property
    def dependency_index(self) -> tuple[list[dict[str, Any]], dict[int, set[int]], dict[int, set[int]], str]:
        with tempfile.TemporaryDirectory(prefix="sentinel-graph-") as directory:
            journal = Path(directory) / "journal.jsonl"
            journal.write_bytes(self.journal)
            graph = build_provenance(journal, 0).to_dict()
        edges = [row for row in graph["edges"] if row["kind"] != "chronological"]
        neighbors: dict[int, set[int]] = {}
        forward: dict[int, set[int]] = {}
        for row in edges:
            neighbors.setdefault(row["source"], set()).add(row["target"])
            neighbors.setdefault(row["target"], set()).add(row["source"])
            forward.setdefault(row["source"], set()).add(row["target"])
        return edges, neighbors, forward, graph["limitation"]

    def provenance(self, *, root_step: int = 0, depth: int = 2) -> dict[str, Any]:
        if not 1 <= depth <= 5 or not 0 <= root_step < len(self.events):
            raise ValueError("graph root or depth outside supported bounds")
        edges, neighbors, forward, limitation = self.dependency_index
        reached = {root_step}
        frontier = {root_step}
        for _ in range(depth):
            following = {neighbor for node in frontier for neighbor in neighbors.get(node, set())} - reached
            reached.update(following)
            if len(reached) > 500:
                raise ValueError("graph neighborhood exceeds budget; choose a smaller depth")
            frontier = following
        selected = [row for row in edges if row["source"] in reached and row["target"] in reached]
        if len(reached) > 500 or len(selected) > 2000:
            raise ValueError("graph neighborhood exceeds budget; choose a smaller depth")
        blast = {root_step}
        frontier = {root_step}
        while frontier:
            following = {target for node in frontier for target in forward.get(node, set())} - blast
            blast.update(following)
            frontier = following
        return {
            "journal_root": self.verified.root,
            "mode": "DECLARED_PROVENANCE_PREVIEW",
            "root_step": root_step,
            "total_nodes": len(self.events),
            "nodes": [self._safe_event(index) for index in sorted(reached)],
            "edges": selected,
            "blast_radius": sorted(blast - {root_step}),
            "limitation": limitation,
        }

    def stream(self, *, after: int = -1, limit: int = 500) -> Iterator[str]:
        if not -1 <= after < max(1, len(self.events)) or not 1 <= limit <= 500:
            raise ValueError("invalid stream cursor or batch limit")
        for index in range(after + 1, min(len(self.events), after + 1 + limit)):
            yield f"id: {index}\nevent: boundary\ndata: {json.dumps(self._safe_event(index))}\n\n"

    def replay(self) -> dict[str, Any]:
        if "pack-definition.json" in self.artifacts:
            from sentinel_replay.pack_capsule import replay_imported_pack
            with tempfile.TemporaryDirectory(prefix="sentinel-imported-pack-") as directory:
                return replay_imported_pack(self.artifacts, self.journal, Path(directory))
        if not self.events or any("request" not in event for event in self.events):
            raise ValueError("exact request payloads are absent; replay is unsupported")
        checkpoints: dict[str, bool] = {}
        with tempfile.TemporaryDirectory(prefix="sentinel-replay-") as directory:
            root = Path(directory)
            imported = root / "imported"
            import_capsule_bytes(self.data, imported)
            store = FileEvidenceStore(root / "blobs")
            for name, value in self.artifacts.items():
                if name.startswith("blob-"):
                    ref = store.put(value)
                    if ref.digest != "sha256:" + name.removeprefix("blob-"):
                        raise ValueError("checkpoint blob identity mismatch")
            for name in ("workspace", "fixture"):
                raw = self.artifacts.get(f"{name}-manifest.json")
                if raw is None:
                    continue
                manifest = WorkspaceManifest.model_validate_json(raw)
                destination = root / name
                restore_workspace(manifest, destination, store)
                checkpoints[name] = verify_workspace(manifest, destination)
            session = BoundarySession.replay(imported / "journal.jsonl")
            for event in self.events:
                if event_digest(event["request"]) != event["request_digest"]:
                    raise ValueError("recorded request payload does not match its digest")
                session.call(
                    event["kind"],
                    event["call_id"],
                    event["request"],
                    evidence=event.get("evidence", {}),
                )
            session.assert_complete()
        return {
            "mode": "BOUNDARY_REPLAY_MATCHED",
            "journal_root": self.verified.root,
            "matched": len(self.events),
            "checkpoints": checkpoints,
            "live_calls": 0,
            "limitation": (
                "Checkpoint bytes and recorded inputs matched; native effects were not re-executed."
            ),
        }
