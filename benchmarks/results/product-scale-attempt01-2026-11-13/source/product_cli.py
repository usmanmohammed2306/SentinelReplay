"""Product commands over the declared local environment pack and evidence API."""

import json
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from sentinel_replay.bisection import FilePredicate, localize_pack
from sentinel_replay.environment_pack import Pack, record_pack, replay_pack
from sentinel_replay.pack_capsule import export_pack
from sentinel_replay.policy_language import Policy
from sentinel_replay.policy_search import search_policies
from sentinel_replay.product_demo import run_product_demo
from sentinel_replay.security_corpus import evaluate_corpus


def register_product_commands(app: typer.Typer) -> None:
    pack_app = typer.Typer(help="Versioned finite environment pack; no arbitrary code execution.")
    app.add_typer(pack_app, name="pack")

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
        source: Path, output: Annotated[Path, typer.Option()], through: int | None = None
    ) -> None:
        """Restore and re-execute only the finite pack's declared covered effects."""
        try:
            result = replay_pack(source, output, through=through)
        except (OSError, ValueError, RuntimeError) as error:
            raise typer.BadParameter(str(error), param_hint="pack replay") from error
        typer.echo(
            f"{result['mode']} matched={result['matched']} "
            f"effects={result['effects_reexecuted']} complete={result['complete_run']}"
        )

    @app.command("bisect")
    def bisect(
        source: Path,
        output: Annotated[Path, typer.Option()],
        predicate: Annotated[str, typer.Option()],
        measure_linear: bool = True,
    ) -> None:
        """Localize a supported file predicate; refuse unjustified binary search."""
        kind, separator, path = predicate.partition(":")
        if not separator:
            raise typer.BadParameter("use file_exists:BASENAME or file_missing:BASENAME")
        try:
            value = FilePredicate.model_validate({"kind": kind, "path": path})
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
        destination: Path, actions: Annotated[int, typer.Option(min=3000, max=50000)] = 3184
    ) -> None:
        """Execute the integrated synthetic investigation; not a production release."""
        controller = Path.cwd() / ".local-controller" / ("demo-" + uuid4().hex)
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
