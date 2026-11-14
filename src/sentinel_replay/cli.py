"""Command-line entry point for Sentinel Replay."""

import importlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

import typer

from sentinel_replay import __version__
from sentinel_replay.aws_evidence import AnchorRef, KmsRootSigner, S3AnchorStore, S3EvidenceStore
from sentinel_replay.boundary import BoundarySession, ReplayMiss
from sentinel_replay.branch_analysis import analyze_branch_experiment
from sentinel_replay.branch_experiment import run_branch_experiment
from sentinel_replay.canonical import CanonicalizationError, event_digest, load_json_unique
from sentinel_replay.capsule import (
    CapsuleError,
    export_capsule,
    import_capsule,
    verify_capsule,
    verify_imported,
)
from sentinel_replay.client_cli import register_client_commands
from sentinel_replay.codex_trace import CodexTraceError, summarize_codex_trace
from sentinel_replay.evidence_store import FileEvidenceStore
from sentinel_replay.gateway_audit import GatewayAuditError, audit_gateway_journal
from sentinel_replay.gateway_reconcile import ReconciliationError, reconcile_gateway_effects
from sentinel_replay.journal import Journal, JournalCorruption
from sentinel_replay.local_anchor import (
    LocalAnchorError,
    create_keypair,
    publish_anchor,
    sign_root,
    verify_anchor,
)
from sentinel_replay.mini_forensics import EvidenceShapeError, investigate_mini
from sentinel_replay.policy import PolicySpec, policy_source_digest
from sentinel_replay.product_cli import register_product_commands
from sentinel_replay.provenance import ProvenanceShapeError, build_provenance
from sentinel_replay.provenance_eval import LabelError, ProvenanceLabels, score_provenance
from sentinel_replay.scripted_agent import run_scripted_agent
from sentinel_replay.signed_capsule import (
    SignedCapsuleError,
    import_signed_capsule,
    sign_capsule,
    verify_signed_capsule,
)
from sentinel_replay.timeline import TimelineShapeError, compress_timeline
from sentinel_replay.workspace_snapshot import (
    WorkspaceManifest,
    capture_workspace,
    restore_workspace,
    verify_workspace,
)

app = typer.Typer(
    add_completion=False,
    help="Counterfactual incident forensics for autonomous AI agents.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
register_product_commands(app)
register_client_commands(app)
journal_app = typer.Typer(help="Append and verify evidence journals.")
app.add_typer(journal_app, name="journal")
mini_app = typer.Typer(help="Study a synthetic agent run one step at a time.")
app.add_typer(mini_app, name="mini")
aws_app = typer.Typer(help="AWS evidence storage and externally signed root anchors.")
app.add_typer(aws_app, name="aws")
workspace_app = typer.Typer(help="Capture and verify bounded regular-file workspaces.")
app.add_typer(workspace_app, name="workspace")
capsule_app = typer.Typer(help="Export capsules and optionally verify detached local signatures.")
app.add_typer(capsule_app, name="capsule")
local_anchor_app = typer.Typer(help="Development Ed25519 root anchors outside an agent workspace.")
app.add_typer(local_anchor_app, name="local-anchor")
codex_app = typer.Typer(help="Inspect bounded Codex CLI event streams without replay claims.")
app.add_typer(codex_app, name="codex")
gateway_app = typer.Typer(help="Audit the limited MCP tool-gateway evidence grammar.")
app.add_typer(gateway_app, name="gateway")
branch_app = typer.Typer(help="Execute isolated synthetic branches and inspect actual effects.")
app.add_typer(branch_app, name="branch")


@branch_app.command("summarize")
def branch_summarize(experiment: Path) -> None:
    """Verify archived source bindings and compare independently inspected effects."""
    try:
        result = analyze_branch_experiment(experiment)
    except (OSError, ValueError, KeyError) as error:
        raise typer.BadParameter(str(error), param_hint="branch evidence") from error
    typer.echo(
        f"{result['mode']} branches={result['population']['branches']} "
        f"world_diffs={len(result['world_diffs'])} report={experiment / 'analysis.json'}"
    )


@branch_app.command("compare")
def branch_compare(
    destination: Path,
    endpoint: str | None = None,
    served_model: str | None = None,
    model_revision: str | None = None,
    seed: int = 11,
    token_file: Path | None = None,
) -> None:
    """Run frozen Docker/OPA branches, with optional trusted loopback inference."""
    try:
        result = run_branch_experiment(
            destination,
            endpoint=endpoint,
            served_model=served_model,
            model_revision=model_revision,
            seed=seed,
            token_file=token_file,
        )
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="branch experiment") from error
    typer.echo(
        f"{result['mode']} completed={result['completed_branches']}/"
        f"{result['planned_branches']} unknown={result['unknown_branches']} "
        f"report={destination / 'comparison.json'}"
    )
    if result["unknown_branches"]:
        raise typer.Exit(code=1)


@app.callback()
def main() -> None:
    """Run Sentinel Replay commands."""


@app.command()
def version() -> None:
    """Print the installed Sentinel Replay version."""
    typer.echo(f"Sentinel Replay {__version__}")


def _read_event(path: Path) -> object:
    try:
        return load_json_unique(path.read_text(encoding="utf-8"))
    except (OSError, CanonicalizationError) as error:
        raise typer.BadParameter(str(error), param_hint="event file") from error


@app.command("hash-event")
def hash_event(path: Path) -> None:
    """Hash one JSON event under the versioned evidence contract."""
    try:
        typer.echo(event_digest(_read_event(path)))
    except CanonicalizationError as error:
        raise typer.BadParameter(str(error), param_hint="event file") from error


@journal_app.command("append")
def journal_append(journal_path: Path, event_path: Path) -> None:
    """Append one JSON event to a verified journal."""
    try:
        result = Journal(journal_path).append(_read_event(event_path))
    except (CanonicalizationError, JournalCorruption, OSError) as error:
        raise typer.BadParameter(str(error), param_hint="journal") from error
    typer.echo(f"APPENDED records={result.records} root={result.root}")


@journal_app.command("verify")
def journal_verify(journal_path: Path) -> None:
    """Verify every record and print the final evidence root."""
    try:
        result = Journal(journal_path).verify()
    except (JournalCorruption, OSError) as error:
        raise typer.BadParameter(str(error), param_hint="journal") from error
    typer.echo(f"CHAIN VALID records={result.records} root={result.root}")


@gateway_app.command("audit")
def gateway_audit(journal_path: Path, policy_path: Path | None = None) -> None:
    """Verify the chain and proposal/decision/result sequence without replay claims."""
    try:
        digest = None
        if policy_path is not None:
            digest = policy_source_digest(
                PolicySpec.model_validate_json(policy_path.read_text(encoding="utf-8"))
            )
        report = audit_gateway_journal(journal_path, expected_policy_digest=digest)
    except (GatewayAuditError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="gateway journal") from error
    typer.echo(json.dumps(report.to_dict(), sort_keys=True))


@gateway_app.command("reconcile")
def gateway_reconcile(journal_path: Path, root: Path, finalize_matched: bool = False) -> None:
    """Inspect exact outbox effects; optionally finalize matched crash-gap results."""
    try:
        report = reconcile_gateway_effects(journal_path, root, finalize_matched=finalize_matched)
    except (
        GatewayAuditError,
        ReconciliationError,
        JournalCorruption,
        OSError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error), param_hint="gateway effect") from error
    typer.echo(json.dumps(report.to_dict(), sort_keys=True))


@local_anchor_app.command("keygen")
def local_anchor_keygen(controller_root: Path, agent_root: Path) -> None:
    """Create a development keypair outside the declared agent workspace."""
    try:
        private, public = create_keypair(controller_root, agent_root)
    except (LocalAnchorError, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="controller root") from error
    typer.echo(f"DEV_LOCAL_KEYPAIR_CREATED private={private} public={public}")


@local_anchor_app.command("sign")
def local_anchor_sign(
    journal_path: Path, run_id: str, private_key: Path, anchor_root: Path, agent_root: Path
) -> None:
    """Sign and publish one exact journal root outside the agent workspace."""
    try:
        verified = Journal(journal_path).verify()
        attestation = sign_root(run_id, verified, private_key, agent_root)
        path = publish_anchor(attestation, anchor_root, agent_root)
    except (LocalAnchorError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="local anchor") from error
    typer.echo(
        f"DEV_LOCAL_ROOT_ANCHORED run={run_id} records={verified.records} "
        f"root={verified.root} key={attestation.key_id} path={path}"
    )


@local_anchor_app.command("verify")
def local_anchor_verify(
    journal_path: Path, run_id: str, public_key: Path, anchor_root: Path
) -> None:
    """Verify a local root signature and exact journal root; freshness is not proven."""
    try:
        verified = Journal(journal_path).verify()
        valid = verify_anchor(run_id, verified, public_key, anchor_root)
    except (LocalAnchorError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="local anchor") from error
    if not valid:
        typer.echo("DEV_LOCAL_ANCHOR_INVALID", err=True)
        raise typer.Exit(code=1)
    typer.echo(
        f"DEV_LOCAL_ANCHOR_VALID run={run_id} records={verified.records} root={verified.root}"
    )


@app.command("timeline")
def timeline(
    journal_path: Path,
    approved_host: Annotated[
        list[str] | None,
        typer.Option(help="Repeat to enable unapproved-egress classification."),
    ] = None,
    output: Annotated[Path | None, typer.Option(help="Write a redacted JSON report here.")] = None,
) -> None:
    """Compress verified boundary metadata into phases without showing response bodies."""
    if output is not None and (output.exists() or output.is_symlink()):
        raise typer.BadParameter("report path already exists", param_hint="--output")
    hosts = frozenset(approved_host) if approved_host is not None else None
    if hosts is not None and (not hosts or any(not host for host in hosts)):
        raise typer.BadParameter("approved hosts must be nonempty", param_hint="--approved-host")
    try:
        report = compress_timeline(journal_path, approved_hosts=hosts)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as destination:
                json.dump(report.to_dict(), destination, sort_keys=True, indent=2)
                destination.write("\n")
                destination.flush()
                os.fsync(destination.fileno())
    except (TimelineShapeError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="journal") from error
    typer.echo(
        f"{report.mode} actions={report.actions} phases={len(report.phases)} "
        f"findings={len(report.findings)} root={report.journal_root}"
    )


@app.command("provenance")
def provenance(
    journal_path: Path,
    root_step: int,
    output: Annotated[
        Path | None, typer.Option(help="Write a redacted declared graph here.")
    ] = None,
) -> None:
    """Build bounded declared dependencies from one verified boundary journal."""
    if output is not None and (output.exists() or output.is_symlink()):
        raise typer.BadParameter("report path already exists", param_hint="--output")
    try:
        report = build_provenance(journal_path, root_step)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as destination:
                json.dump(report.to_dict(), destination, sort_keys=True, indent=2)
                destination.write("\n")
                destination.flush()
                os.fsync(destination.fileno())
    except (ProvenanceShapeError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="journal") from error
    typer.echo(
        f"{report.mode} nodes={report.nodes} edges={len(report.edges)} "
        f"blast_radius={report.blast_radius} root={report.journal_root}"
    )


@app.command("provenance-score")
def provenance_score(
    journal_path: Path,
    root_step: int,
    labels_path: Path,
    output: Annotated[
        Path | None, typer.Option(help="Write the redacted score and denominators here.")
    ] = None,
) -> None:
    """Score declared dependency pairs against separately authored labels."""
    if output is not None and (output.exists() or output.is_symlink()):
        raise typer.BadParameter("report path already exists", param_hint="--output")
    try:
        labels = ProvenanceLabels.model_validate(
            load_json_unique(labels_path.read_text(encoding="utf-8"))
        )
        score = score_provenance(build_provenance(journal_path, root_step), labels)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as destination:
                json.dump(score.to_dict(), destination, sort_keys=True, indent=2)
                destination.write("\n")
                destination.flush()
                os.fsync(destination.fileno())
    except (
        CanonicalizationError,
        JournalCorruption,
        ProvenanceShapeError,
        LabelError,
        OSError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error), param_hint="provenance labels") from error
    f1 = "undefined" if score.f1 is None else f"{score.f1:.4f}"
    typer.echo(
        f"{score.mode} tp={score.true_positive} fp={score.false_positive} "
        f"fn={score.false_negative} f1={f1} root={score.journal_root}"
    )


@codex_app.command("inspect")
def codex_inspect(
    trace_path: Path,
    output: Annotated[
        Path | None, typer.Option(help="Write a metadata-only observation summary here.")
    ] = None,
) -> None:
    """Summarize a Codex exec --json trace; do not call it a replay recording."""
    if output is not None and (output.exists() or output.is_symlink()):
        raise typer.BadParameter("report path already exists", param_hint="--output")
    try:
        summary = summarize_codex_trace(trace_path)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as destination:
                json.dump(summary.to_dict(), destination, sort_keys=True, indent=2)
                destination.write("\n")
                destination.flush()
                os.fsync(destination.fileno())
    except (CodexTraceError, OSError) as error:
        raise typer.BadParameter(str(error), param_hint="Codex trace") from error
    typer.echo(
        f"{summary.mode} events={summary.events} "
        f"commands={summary.commands_completed} files={summary.file_changes_completed} "
        f"turn={summary.turn_status} digest={summary.trace_digest}"
    )


@capsule_app.command("export")
def capsule_export(
    run_id: str,
    journal_path: Path,
    destination: Path,
    artifact: Annotated[
        list[str] | None,
        typer.Option(help="Repeat NAME=PATH for bounded investigation artifacts."),
    ] = None,
) -> None:
    """Export a verified journal and named files without claiming a signature."""
    sources: dict[str, Path] = {}
    for item in artifact or []:
        if "=" not in item:
            raise typer.BadParameter("artifact must be NAME=PATH", param_hint="--artifact")
        name, path = item.split("=", 1)
        if name in sources:
            raise typer.BadParameter("duplicate artifact name", param_hint="--artifact")
        sources[name] = Path(path)
    try:
        result = export_capsule(run_id, journal_path, destination, sources)
    except (CapsuleError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="capsule") from error
    typer.echo(
        f"UNSIGNED_CAPSULE_EXPORTED run={result.run_id} records={result.records} "
        f"root={result.root} artifacts={result.artifacts} path={destination}"
    )


@capsule_app.command("verify")
def capsule_verify(path: Path) -> None:
    """Verify every archive entry and journal hash offline; not authenticity."""
    try:
        result = verify_capsule(path)
    except (CapsuleError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="capsule") from error
    typer.echo(
        f"UNSIGNED_CAPSULE_INTEGRITY_VALID run={result.run_id} records={result.records} "
        f"root={result.root} artifacts={result.artifacts}"
    )


@capsule_app.command("sign-local")
def capsule_sign_local(
    capsule_path: Path, private_key: Path, anchor_root: Path, agent_root: Path
) -> None:
    """Create a detached development signature over the complete capsule bytes."""
    try:
        attestation = sign_capsule(capsule_path, private_key, anchor_root, agent_root)
    except (SignedCapsuleError, OSError) as error:
        raise typer.BadParameter(str(error), param_hint="capsule signature") from error
    typer.echo(f"DEV_LOCAL_CAPSULE_SIGNED attestation={attestation}")


@capsule_app.command("verify-signed")
def capsule_verify_signed(capsule_path: Path, attestation: Path, public_key: Path) -> None:
    """Check a detached signature using an explicitly trusted public key."""
    try:
        valid = verify_signed_capsule(capsule_path, attestation, public_key)
    except (SignedCapsuleError, OSError) as error:
        raise typer.BadParameter(str(error), param_hint="capsule signature") from error
    if not valid:
        typer.echo("DEV_LOCAL_CAPSULE_SIGNATURE_INVALID", err=True)
        raise typer.Exit(code=1)
    typer.echo("DEV_LOCAL_CAPSULE_SIGNATURE_VALID")


@capsule_app.command("witness")
def capsule_witness(
    capsule_path: Path, attestation: Path, public_key: Path, witness_root: Path, agent_root: Path
) -> None:
    """Authenticate and pin one final capsule per run in operator-held storage."""
    from sentinel_replay.capsule_witness import publish_witness

    try:
        path = publish_witness(capsule_path, attestation, public_key, witness_root, agent_root)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="operator witness") from error
    typer.echo(f"CAPSULE_WITNESSED path={path}")


@capsule_app.command("import-signed")
def capsule_import_signed(
    capsule_path: Path, attestation: Path, public_key: Path, destination: Path
) -> None:
    """Authenticate and import the same complete archive bytes."""
    try:
        result = import_signed_capsule(capsule_path, attestation, public_key, destination)
    except (SignedCapsuleError, CapsuleError, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="signed capsule") from error
    typer.echo(
        f"DEV_LOCAL_SIGNED_CAPSULE_IMPORTED run={result.run_id} records={result.records} "
        f"root={result.root} destination={destination}"
    )


@capsule_app.command("import")
def capsule_import(path: Path, destination: Path) -> None:
    """Reject unverified or unsafe archives before creating an import directory."""
    try:
        result = import_capsule(path, destination)
    except (CapsuleError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="capsule") from error
    typer.echo(
        f"UNSIGNED_CAPSULE_IMPORTED run={result.run_id} records={result.records} "
        f"root={result.root} destination={destination}"
    )


@capsule_app.command("replay-imported")
def capsule_replay_imported(scenario: str, destination: Path) -> None:
    """Verify an imported mini-agent capsule and replay its recorded boundaries."""
    scenario = _mini_scenario(scenario)
    try:
        verified = verify_imported(destination)
        replayed = run_scripted_agent(
            BoundarySession.replay(destination / "journal.jsonl"),
            allow_live=False,
            scenario=scenario,
        )
    except (CapsuleError, ReplayMiss, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="imported capsule") from error
    typer.echo(
        f"BOUNDARY_REPLAY_MATCHED run={verified.run_id} scenario={scenario} "
        f"actions={replayed.actions} signature={replayed.signature} root={verified.root}"
    )


@app.command("boundary-demo")
def boundary_demo(
    record: Annotated[Path | None, typer.Option(help="Record one example tool call here.")] = None,
    replay: Annotated[Path | None, typer.Option(help="Replay from an existing recording.")] = None,
) -> None:
    """Exercise one fail closed tool boundary."""
    if (record is None) == (replay is None):
        raise typer.BadParameter("choose exactly one of --record or --replay")
    request = {"tool": "read_file", "path": "README.md"}
    path = record if record is not None else replay
    assert path is not None
    try:
        if record is not None:
            if path.exists():
                raise typer.BadParameter("recording path already exists", param_hint="--record")
            with BoundarySession.record_stream(path) as session:
                result = session.call(
                    "tool", "demo-read-1", request, lambda: {"content": "Sentinel Replay"}
                )
            mode = "RECORDED"
        else:
            session = BoundarySession.replay(path)
            result = session.call("tool", "demo-read-1", request)
            session.assert_complete()
            mode = "BOUNDARY_REPLAY_MATCHED"
    except (ReplayMiss, JournalCorruption, CanonicalizationError, OSError) as error:
        raise typer.BadParameter(str(error), param_hint="recording") from error
    typer.echo(f"{mode} {result}")


def _mini_scenario(scenario: str) -> str:
    if scenario not in {"incident", "benign"}:
        raise typer.BadParameter("scenario must be incident or benign")
    return scenario


@mini_app.command("record")
def mini_record(scenario: str, recording: Path) -> None:
    """Record synthetic boundary responses for one named scenario."""
    scenario = _mini_scenario(scenario)
    if recording.exists():
        raise typer.BadParameter("recording path already exists", param_hint="recording")
    try:
        with BoundarySession.record_stream(recording) as session:
            run = run_scripted_agent(session, allow_live=True, scenario=scenario)
    except (CanonicalizationError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="recording") from error
    typer.echo(f"RECORDED scenario={scenario} actions={run.actions} signature={run.signature}")


@mini_app.command("inspect")
def mini_inspect(recording: Path) -> None:
    """Inspect verified metadata without printing recorded response bodies."""
    try:
        journal = Journal(recording)
        result = journal.verify()
        events = journal.events()
    except (JournalCorruption, OSError) as error:
        raise typer.BadParameter(str(error), param_hint="recording") from error
    typer.echo(f"CHAIN VALID records={result.records} root={result.root}")
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise typer.BadParameter(f"invalid boundary at {index}", param_hint="recording")
        kind = event.get("kind")
        call_id = event.get("call_id")
        request_digest = event.get("request_digest")
        if not all(isinstance(value, str) for value in (kind, call_id, request_digest)):
            raise typer.BadParameter(f"invalid boundary at {index}", param_hint="recording")
        typer.echo(f"{index}: {kind} {call_id} request={request_digest}")


@mini_app.command("replay")
def mini_replay(scenario: str, recording: Path) -> None:
    """Replay from evidence only; never invoke a synthetic live callback."""
    scenario = _mini_scenario(scenario)
    try:
        run = run_scripted_agent(
            BoundarySession.replay(recording), allow_live=False, scenario=scenario
        )
        root = Journal(recording).verify().root
    except (ReplayMiss, CanonicalizationError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="recording") from error
    typer.echo(
        f"BOUNDARY_REPLAY_MATCHED scenario={scenario} actions={run.actions} "
        f"signature={run.signature} journal_root={root}"
    )


@mini_app.command("investigate")
def mini_investigate(
    incident_recording: Path,
    benign_recording: Path,
    output: Annotated[Path | None, typer.Option(help="Write a redacted JSON report here.")] = None,
) -> None:
    """Explain one synthetic incident and compare bounded recorded-trace policies."""
    if output is not None and output.exists():
        raise typer.BadParameter("report path already exists", param_hint="--output")
    try:
        report = investigate_mini(incident_recording, benign_recording)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as destination:
                json.dump(report.to_dict(), destination, sort_keys=True, indent=2)
                destination.write("\n")
                destination.flush()
                os.fsync(destination.fileno())
    except (EvidenceShapeError, JournalCorruption, OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="recording") from error
    finding = report.incident
    typer.echo(
        f"{report.mode} incident={'yes' if finding else 'no'} "
        f"root_step={finding.root_step if finding else 'none'} "
        f"egress_step={finding.egress_step if finding else 'none'} "
        f"blast_radius={report.blast_radius} frontier={','.join(report.frontier) or 'none'}"
    )


@app.command("demo-mini")
def demo_mini(output: Path) -> None:
    """Record and strictly replay synthetic incident and benign trajectories."""
    if output.exists() and any(output.iterdir()):
        raise typer.BadParameter("demo output directory is not empty", param_hint="output")
    output.mkdir(parents=True, exist_ok=True)
    for scenario in ("incident", "benign"):
        recording = output / f"{scenario}.jsonl"
        with BoundarySession.record_stream(recording) as session:
            recorded = run_scripted_agent(session, allow_live=True, scenario=scenario)
        for _ in range(2):
            replayed = run_scripted_agent(
                BoundarySession.replay(recording), allow_live=False, scenario=scenario
            )
            if recorded != replayed:
                raise typer.Exit(code=1)
        root = Journal(recording).verify().root
        typer.echo(
            f"BOUNDARY_REPLAY_MATCHED scenario={scenario} actions={replayed.actions} "
            f"replays=2 signature={replayed.signature} journal_root={root}"
        )


def _aws_clients(region: str) -> tuple[Any, Any]:
    """Load optional SDK only for explicit AWS commands; use standard credential chain."""
    if not region:
        raise typer.BadParameter("an explicit AWS region is required")
    try:
        boto3 = importlib.import_module("boto3")
    except ModuleNotFoundError as error:
        raise typer.BadParameter("install the AWS extra: uv sync --extra aws") from error
    session = boto3.Session(region_name=region)
    return session.client("s3"), session.client("kms")


def _distinct_keys(encryption_key_arn: str, signing_key_arn: str) -> None:
    if encryption_key_arn == signing_key_arn:
        raise typer.BadParameter("encryption and asymmetric signing keys must differ")


@aws_app.command("put-blob")
def aws_put_blob(
    source: Path,
    bucket: Annotated[str, typer.Option(help="Versioned evidence bucket name.")],
    encryption_key_arn: Annotated[str, typer.Option(help="Symmetric KMS encryption key ARN.")],
    region: Annotated[str, typer.Option(help="Explicit AWS region.")],
) -> None:
    """Store one small evidence blob by SHA-256 with SSE-KMS and conditional creation."""
    try:
        s3, _ = _aws_clients(region)
        data = source.read_bytes()
        reference = S3EvidenceStore(s3, bucket, encryption_key_arn).put(data)
    except Exception as error:
        raise typer.BadParameter(str(error), param_hint="AWS evidence") from error
    typer.echo(
        f"AWS_BLOB_STORED digest={reference.digest} size={reference.size} "
        f"version={reference.version_id or 'unversioned'}"
    )


@aws_app.command("anchor-journal")
def aws_anchor_journal(
    journal_path: Path,
    run_id: str,
    reference_path: Path,
    bucket: Annotated[str, typer.Option(help="Separate versioned anchor bucket name.")],
    encryption_key_arn: Annotated[str, typer.Option(help="Symmetric KMS encryption key ARN.")],
    signing_key_arn: Annotated[str, typer.Option(help="Asymmetric KMS signing key ARN.")],
    region: Annotated[str, typer.Option(help="Explicit AWS region.")],
) -> None:
    """Sign a verified journal root and publish its attestation as an exact S3 version."""
    _distinct_keys(encryption_key_arn, signing_key_arn)
    if reference_path.exists():
        raise typer.BadParameter("reference path already exists", param_hint="reference")
    try:
        verified = Journal(journal_path).verify()
        s3, kms = _aws_clients(region)
        signer = KmsRootSigner(kms, signing_key_arn)
        attestation = signer.sign(run_id, verified)
        if not signer.verify(attestation):
            raise ValueError("KMS could not verify its new root signature")
        reference = S3AnchorStore(s3, bucket, encryption_key_arn).publish(attestation)
        reference_path.parent.mkdir(parents=True, exist_ok=True)
        with reference_path.open("x", encoding="utf-8") as destination:
            json.dump(asdict(reference), destination, sort_keys=True)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
    except Exception as error:
        raise typer.BadParameter(str(error), param_hint="AWS anchor") from error
    typer.echo(
        f"AWS_ANCHOR_PUBLISHED run={run_id} records={verified.records} "
        f"root={verified.root} version={reference.version_id} reference={reference_path}"
    )


@aws_app.command("verify-anchor")
def aws_verify_anchor(
    journal_path: Path,
    run_id: str,
    reference_path: Path,
    bucket: Annotated[str, typer.Option(help="Separate versioned anchor bucket name.")],
    encryption_key_arn: Annotated[str, typer.Option(help="Symmetric KMS encryption key ARN.")],
    signing_key_arn: Annotated[str, typer.Option(help="Asymmetric KMS signing key ARN.")],
    region: Annotated[str, typer.Option(help="Explicit AWS region.")],
) -> None:
    """Compare the local journal to a version-pinned, KMS-verified remote anchor."""
    _distinct_keys(encryption_key_arn, signing_key_arn)
    try:
        verified = Journal(journal_path).verify()
        reference = AnchorRef(**json.loads(reference_path.read_text(encoding="utf-8")))
        s3, kms = _aws_clients(region)
        attestation = S3AnchorStore(s3, bucket, encryption_key_arn).load(reference)
        if attestation.run_id != run_id:
            raise ValueError("run ID differs from AWS anchor")
        if attestation.root != verified.root or attestation.records != verified.records:
            raise ValueError("journal root or count differs from AWS anchor")
        if not KmsRootSigner(kms, signing_key_arn).verify(attestation):
            raise ValueError("KMS signature verification failed")
    except Exception as error:
        raise typer.BadParameter(str(error), param_hint="AWS anchor") from error
    typer.echo(
        f"AWS_ANCHOR_VALID run={attestation.run_id} records={verified.records} "
        f"root={verified.root} version={reference.version_id}"
    )


@workspace_app.command("snapshot")
def workspace_snapshot(source: Path, store_root: Path, manifest_path: Path) -> None:
    """Capture regular files into a local content-addressed store."""
    if manifest_path.exists():
        raise typer.BadParameter("manifest path already exists", param_hint="manifest")
    try:
        manifest = capture_workspace(source, FileEvidenceStore(store_root))
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("x", encoding="utf-8") as destination:
            destination.write(manifest.model_dump_json(indent=2) + "\n")
            destination.flush()
            os.fsync(destination.fileno())
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="workspace") from error
    typer.echo(
        f"WORKSPACE_CAPTURED files={len(manifest.entries)} digest={manifest.manifest_digest} "
        f"coverage={manifest.coverage}"
    )


@workspace_app.command("restore")
def workspace_restore(manifest_path: Path, store_root: Path, destination: Path) -> None:
    """Preflight all blobs, then restore and verify in a new directory."""
    try:
        manifest = WorkspaceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        restore_workspace(manifest, destination, FileEvidenceStore(store_root))
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="workspace") from error
    typer.echo(
        f"WORKSPACE_BYTES_RESTORED files={len(manifest.entries)} "
        f"digest={manifest.manifest_digest} destination={destination}"
    )


@workspace_app.command("verify")
def workspace_verify(manifest_path: Path, root: Path) -> None:
    """Verify exact regular-file bytes and executable flags under a manifest."""
    try:
        manifest = WorkspaceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        matching = verify_workspace(manifest, root)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="workspace") from error
    if not matching:
        typer.echo("WORKSPACE_BYTES_MISMATCH", err=True)
        raise typer.Exit(code=1)
    typer.echo(
        f"WORKSPACE_BYTES_VERIFIED files={len(manifest.entries)} digest={manifest.manifest_digest}"
    )
