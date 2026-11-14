"""Recorded nondeterministic calls with strict fail closed replay."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from sentinel_replay.canonical import event_digest
from sentinel_replay.journal import Journal, JournalWriter


class ReplayMiss(RuntimeError):
    """No compatible recorded response exists for this boundary call."""


class BoundarySession:
    def __init__(self, path: Path, mode: str, *, writer: JournalWriter | None = None) -> None:
        if mode not in {"record", "replay"}:
            raise ValueError(f"unknown boundary mode: {mode}")
        if writer is not None and mode != "record":
            raise ValueError("a journal writer is only valid in record mode")
        self._journal = Journal(path)
        self._mode = mode
        self._writer = writer
        if writer is not None:
            if writer.path != path or writer.verification is None:
                raise ValueError("journal writer must be open for the same path")
            self._recordings: list[object] = []
            self._cursor = writer.verification.records
        else:
            self._recordings = self._journal.events()
            self._cursor = len(self._recordings) if mode == "record" else 0

    @classmethod
    def record(cls, path: Path) -> "BoundarySession":
        return cls(path, "record")

    @classmethod
    @contextmanager
    def record_stream(cls, path: Path) -> Iterator["BoundarySession"]:
        """Record with one exclusive chain scan and a durable append per call."""
        with Journal(path).writer() as writer:
            yield cls(path, "record", writer=writer)

    @classmethod
    def replay(cls, path: Path) -> "BoundarySession":
        return cls(path, "replay")

    def call(
        self,
        kind: str,
        call_id: str,
        request: object,
        live: Callable[[], object] | None = None,
        *,
        evidence: dict[str, object] | None = None,
    ) -> object:
        """Invoke once during recording; use only matching evidence during replay."""
        request_digest = event_digest(request)
        safe_evidence = evidence if evidence is not None else {}
        evidence_digest = event_digest(safe_evidence)
        if self._mode == "record":
            if live is None:
                raise ValueError("recording requires a live call")
            response = live()
            event = {
                "kind": kind,
                "call_id": call_id,
                "sequence": self._cursor,
                "request_digest": request_digest,
                "evidence": safe_evidence,
                "response": response,
            }
            if self._writer is None:
                self._journal.append(event)
            else:
                self._writer.append(event)
            self._cursor += 1
            return response

        if self._cursor >= len(self._recordings):
            raise ReplayMiss(f"recording exhausted at call {self._cursor}: {call_id}")
        row = self._recordings[self._cursor]
        if not isinstance(row, dict):
            raise ReplayMiss(f"invalid recording at call {self._cursor}")
        for field, expected in (
            ("sequence", self._cursor),
            ("kind", kind),
            ("call_id", call_id),
            ("request_digest", request_digest),
        ):
            if row.get(field) != expected:
                raise ReplayMiss(
                    f"{field.replace('_', ' ')} mismatch at call {self._cursor}: {call_id}"
                )
        if event_digest(row.get("evidence", {})) != evidence_digest:
            raise ReplayMiss(f"evidence mismatch at call {self._cursor}: {call_id}")
        if "response" not in row:
            raise ReplayMiss(f"missing response at call {self._cursor}: {call_id}")
        self._cursor += 1
        return row["response"]

    def assert_complete(self) -> None:
        """Reject a replay that silently leaves recorded calls unused."""
        if self._mode == "replay" and self._cursor != len(self._recordings):
            raise ReplayMiss(
                f"replay stopped after {self._cursor} of {len(self._recordings)} calls"
            )
