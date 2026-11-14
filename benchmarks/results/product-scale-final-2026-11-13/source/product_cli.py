"""Product commands over the declared local environment pack and evidence API."""

import json
import tempfile
from functools import partial
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from sentinel_replay.bisection import FilePredicate, localize_pack
from sentinel_replay.capsule import read_capsule_bytes
from sentinel_replay.checkpoint_set import restore_checkpoint_set
from sentinel_replay.environment_pack import Pack, record_pack, replay_pack
from sentinel_replay.investigation import CapsuleInvestigation
from sentinel_replay.local_anchor import _regular_bytes
from sentinel_replay.pack_capsule import export_pack, materialize_pack
from sentinel_replay.policy_language import Policy
from sentinel_replay.policy_search import search_policies
from sentinel_replay.product_demo import run_product_demo
from sentinel_replay.security_corpus import evaluate_corpus


def register_product_commands(app: typer.Typer) -> None:
    pack_app = typer.Typer(help="Versioned finite environment pack; no arbitrary code execution.")
    app.add_typer(pack_app, name="pack")

    @app.command("record")
    def record(
        output: Annotated[Path, typer.Option()],
        program: Path | None = None,
        policy: Path | None = None,
        adapter: str = "finite",
        endpoint: str | None = None,
        served_model: str | None = None,
        model_revision: str | None = None,
        token_file: Path | None = None,
        seed: int = 11,
        signing_key: Path | None = None,
        anchor_root: Path | None = None,
    ) -> None:
        """Record a declared finite pack or the bounded isolated coding-agent cohort."""
        if adapter == "finite":
            if program is None or policy is None:
                raise typer.BadParameter("finite recording requires --program and --policy")
            result = record_pack(
                Pack.model_validate_json(_regular_bytes(program, 32 * 1024 * 1024)),
                output,
                Policy.model_validate_json(_regular_bytes(policy, 65536)),
                signing_key=signing_key,
                anchor_root=anchor_root,
            )
            typer.echo(
                f"{result['mode']} records={result['records']} status={result['status']} "
                f"root={result['journal_root']}"
            )
        elif adapter == "isolated-coding":
            from sentinel_replay.branch_experiment import run_branch_experiment

            if program is not None or policy is not None:
                raise typer.BadParameter(
                    "isolated-coding uses its frozen three-scenario/three-policy cohort"
                )
            result = run_branch_experiment(
                output,
                endpoint=endpoint,
                served_model=served_model,
                model_revision=model_revision,
                token_file=token_file,
                seed=seed,
            )
            typer.echo(
                f"{result['mode']} completed={result['completed_branches']}/"
                f"{result['planned_branches']} unknown={result['unknown_branches']}"
            )
            if result["unknown_branches"]:
                raise typer.Exit(code=1)
        else:
            raise typer.BadParameter("no covered adapter; choose finite or isolated-coding")

    @pack_app.command("record")
    def pack_record(program: Path, policy: Path, destination: Path) -> None:
        result = record_pack(
            Pack.model_validate_json(program.read_text()),
            destination,
            Policy.model_validate_json(policy.read_text()),
        )
        typer.echo(
            f"{result['mode']} status={result['status']} records={result['records']} "
            f"root={result['journal_root']}"
        )

    @pack_app.command("export")
    def pack_export(source: Path, destination: Path) -> None:
        result = export_pack(source, destination)
        typer.echo(f"PACK_CAPSULE_EXPORTED run={result['run_id']} records={result['records']}")

    @app.command("security-corpus")
    def security_corpus(destination: Path) -> None:
        """Run all twelve synthetic cases with real OPA; keep unsupported outcomes."""
        result = evaluate_corpus(destination)
        typer.echo(
            json.dumps(
                {
                    "cases": result["case_denominator"],
                    "branches": result["branch_denominator"],
                    "scores": result["scores"],
                },
                indent=2,
            )
        )

    @app.command("policy-search")
    def policy_search(
        destination: Path,
        max_candidates: Annotated[int, typer.Option(min=1, max=1000)] = 128,
        time_budget: Annotated[int, typer.Option(min=1, max=600)] = 600,
        resume: bool = False,
    ) -> None:
        """Execute a bounded greedy candidate neighborhood on the known corpus."""
        result = search_policies(
            destination,
            max_candidates=max_candidates,
            time_budget_seconds=time_budget,
            resume=resume,
        )
        typer.echo(
            f"POLICY_SEARCH tested={len(result['scores'])} partial={result['partial']} "
            f"frontier={len(result['frontier'])} report={destination / 'progress.json'}"
        )
        if result["failures"]:
            raise typer.Exit(code=1)

    @app.command("replay")
    def replay(
        source: Path,
        output: Annotated[Path, typer.Option()],
        through: int | None = None,
        from_step: Annotated[int, typer.Option("--from", min=0, max=50000)] = 0,
        policy: Path | None = None,
    ) -> None:
        """Restore and re-execute only the finite pack's declared covered effects."""
        try:
            if source.is_file():
                investigation = CapsuleInvestigation(read_capsule_bytes(source))
                if policy is not None:
                    if through is not None:
                        raise ValueError("--through cannot be combined with a policy fork")
                    from sentinel_replay.futures import simulate_future

                    result = simulate_future(
                        investigation,
                        Policy.model_validate_json(_regular_bytes(policy, 65536)),
                        output,
                        fork_step=from_step,
                    )
                    typer.echo(
                        f"{result['mode']} changed_paths={len(result['world_diff'])} "
                        f"status={result['status']}"
                    )
                    return
                if "pack-definition.json" not in investigation.artifacts:
                    if through is not None or from_step:
                        raise ValueError("this branch adapter has no covered prefix replay")
                    result = investigation.replay()
                    output.mkdir(mode=0o700, parents=True, exist_ok=False)
                else:
                    output.mkdir(mode=0o700, parents=True, exist_ok=False)
                    pack = materialize_pack(investigation.artifacts, investigation.journal, output)
                    restore = partial(restore_checkpoint_set, investigation.artifacts)
                    if from_step:
                        replay_pack(
                            pack, output / "prefix", through=from_step, extra_restore=restore
                        )
                    result = replay_pack(
                        pack, output / "restored", through=through, extra_restore=restore
                    )
                (output / "replay-report.json").write_text(json.dumps(result, indent=2) + "\n")
            else:
                if policy is not None or from_step:
                    raise ValueError("policy forks and --from require a portable capsule")
                result = replay_pack(source, output, through=through)
        except (OSError, ValueError, RuntimeError) as error:
            raise typer.BadParameter(str(error), param_hint="pack replay") from error
        typer.echo(
            f"{result['mode']} matched={result['matched']} "
            f"effects={result.get('effects_reexecuted', 'not_reexecuted')} "
            f"complete={result.get('complete_run', True)}"
        )

    @app.command("bisect")
    def bisect(
        source: Path,
        output: Annotated[Path, typer.Option()],
        predicate: Annotated[str, typer.Option()],
        measure_linear: bool = False,
    ) -> None:
        """Localize a supported file predicate; refuse unjustified binary search."""
        kind, separator, path = predicate.partition(":")
        if not separator:
            raise typer.BadParameter("use file_exists:BASENAME or file_missing:BASENAME")
        try:
            value = FilePredicate.model_validate({"kind": kind, "path": path})
            if source.is_file():
                investigation = CapsuleInvestigation(read_capsule_bytes(source))
                with tempfile.TemporaryDirectory(prefix="sentinel-cli-bisect-") as directory:
                    pack = materialize_pack(
                        investigation.artifacts, investigation.journal, Path(directory)
                    )
                    result = localize_pack(
                        pack,
                        output,
                        value,
                        measure_linear=measure_linear,
                        extra_restore=partial(restore_checkpoint_set, investigation.artifacts),
                    )
            else:
                result = localize_pack(source, output, value, measure_linear=measure_linear)
        except (OSError, ValueError, RuntimeError) as error:
            raise typer.BadParameter(str(error), param_hint="prefix localization") from error
        typer.echo(
            f"PREFIX_LOCALIZATION first={result['first_true_prefix']} "
            f"binary_restores={result['binary_restores']} "
            f"linear_restores={result['linear_restores']}"
        )

    @app.command("demo")
    def demo(
        destination: Path | None = None,
        actions: Annotated[int, typer.Option(min=3000, max=10000)] = 3184,
    ) -> None:
        """Execute the integrated synthetic investigation; not a production release."""
        controller = Path.cwd() / ".local-controller" / ("demo-" + uuid4().hex)
        destination = destination or Path.cwd() / ".local-controller/demos" / uuid4().hex
        try:
            result = run_product_demo(destination, controller, actions=actions)
        except (OSError, ValueError, RuntimeError) as error:
            raise typer.BadParameter(str(error), param_hint="investigation demo") from error
        typer.echo(
            f"{result['status']} actions={result['program_actions']} "
            f"boundaries={result['boundary_records']} release={result['release_status']} "
            f"report={destination / 'demo-report.json'}"
        )
        if result["status"] != "WORKFLOW_DEMO_PASS":
            raise typer.Exit(code=1)
