"""Restore-counted prefix localization with a restricted, validated predicate.

An existence predicate is monotone only when the pack cannot delete its target;
absence is monotone only when the pack cannot write it. Otherwise use an explicit
linear fallback. No arbitrary predicate code from an investigator is executed.
"""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sentinel_replay.environment_pack import Pack, replay_pack


class FilePredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["file_exists", "file_missing"]
    path: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

    @model_validator(mode="after")
    def safe(self) -> "FilePredicate":
        if (
            self.path in {".", ".."}
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", self.path) is None
        ):
            raise ValueError("predicate requires a regular-file basename")
        return self

    def evaluate(self, world: Path) -> bool:
        exists = (world / self.path).is_file()
        return exists if self.kind == "file_exists" else not exists


def localize_pack(
    source: Path,
    destination: Path,
    predicate: FilePredicate,
    *,
    measure_linear: bool = True,
    extra_restore: Callable[[Path, dict[str, str]], dict[str, bool]] | None = None,
) -> dict[str, Any]:
    definition = json.loads((source / "definition.json").read_text())
    pack = Pack.model_validate(definition["pack"])
    mutators = [
        step.action.operation
        for step in pack.steps
        if step.action.resource == predicate.path and step.action.operation != "read_file"
    ]
    writes = {"write_file", "http_post", "artifact_export", "handoff", "env_set", "git_write"}
    monotone = (
        all(op in writes for op in mutators)
        if predicate.kind == "file_exists"
        else all(op == "delete_file" for op in mutators)
    )
    if len(pack.steps) > 512 and (not monotone or measure_linear):
        raise ValueError("linear localization exceeds 512-step validation budget")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    probes: list[dict[str, Any]] = []

    def probe(count: int, method: str) -> bool:
        target = destination / f"{method}-{len(probes):04d}"
        receipt = replay_pack(source, target, through=count, extra_restore=extra_restore)
        value = predicate.evaluate(target / "world")
        probes.append({"method": method, "through": count, "predicate": value, "replay": receipt})
        return value

    first: int | None = None
    if monotone:
        if probe(0, "binary"):
            first = 0
        elif probe(len(pack.steps), "binary"):
            low, high = 1, len(pack.steps)
            while low < high:
                middle = (low + high) // 2
                if probe(middle, "binary"):
                    high = middle
                else:
                    low = middle + 1
            first = low
    linear_first = None
    if not monotone or measure_linear:
        for count in range(len(pack.steps) + 1):
            if probe(count, "linear"):
                linear_first = count
                break
        if monotone and linear_first != first:
            raise ValueError("static monotonicity prediction disagrees with restored linear scan")
        if not monotone:
            first = linear_first
    result = {
        "mode": "VERIFIED_REPLAY",
        "predicate": predicate.model_dump(),
        "monotonicity": "validated_by_finite_mutation_contract"
        if monotone
        else "unproven_linear_fallback",
        "first_true_prefix": first,
        "incident_program_step": first - 1 if first else None,
        "binary_restores": sum(row["method"] == "binary" for row in probes),
        "linear_restores": sum(row["method"] == "linear" for row in probes),
        "probes": probes,
        "limitation": (
            "Localization of the supplied file predicate; not independent causal root discovery."
        ),
    }
    (destination / "localization.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result
