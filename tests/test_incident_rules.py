from pathlib import Path

from sentinel_replay.environment_pack import record_pack
from sentinel_replay.incident_rules import classify_incidents
from sentinel_replay.journal import Journal
from sentinel_replay.security_corpus import corpus_cases, policies


def test_frozen_rule_catalog_covers_known_fixture_cases_and_retains_unknown(tmp_path: Path) -> None:
    positives = 0
    for case in corpus_cases():
        source = tmp_path / case.pack.name
        # All-allow fixture vector is not an OPA enforcement measurement.
        report = record_pack(
            case.pack,
            source,
            policies()["allow_all"],
            decisions=["allowed"] * len(case.pack.steps),
            decision_source="test_fixture",
        )
        events = [
            event for event in Journal(source / "journal.jsonl").events() if isinstance(event, dict)
        ]
        result = classify_incidents(
            events, case.pack.name, report["journal_root"], finite_pack=True
        )
        expected = case.predicate not in {"none", "unsupported"}
        assert bool(result["incidents"]) == expected, case.pack.name
        positives += expected
        if case.predicate == "unsupported":
            assert report["status"] == "unknown"
    assert positives == 9
