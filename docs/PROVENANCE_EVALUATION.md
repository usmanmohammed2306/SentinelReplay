# Provenance edge evaluation protocol

Sentinel can now score its declared dependency graph against a separately authored label file. This measures agreement with labels, not universal causality. The current mini-agent fixture is useful for testing the arithmetic; it is not an independently labeled public benchmark.

The label file identifies the exact verified journal root and node count. Each positive label is a forward directed pair with a typed reason (`dataflow`, `filesystem`, `effect`, `trace_parent`, or `control`). The score compares directed pairs from non-chronological predicted edges with labeled positive pairs. Chronological edges are counted separately and never enter precision, recall, F1, or blast-radius reachability.

```json
{
  "schema_version": 1,
  "journal_root": "sha256:REPLACE_WITH_THE_VERIFIED_64_HEX_DIGEST",
  "nodes": 5,
  "labeled_by": "name or versioned labeling protocol",
  "dependencies": [
    {"source": 2, "target": 3, "kind": "dataflow"},
    {"source": 3, "target": 4, "kind": "control"}
  ]
}
```

After independently checking the trace and filling in real labels, run `sentinel provenance-score JOURNAL ROOT_STEP LABELS.json --output SCORE.json`. The result names true positives, false positives, false negatives, and the exact journal root. Precision uses `TP / (TP + FP)`; recall uses `TP / (TP + FN)`; F1 uses `2TP / (2TP + FP + FN)`. A zero denominator is reported as `null` or `undefined`, not as perfect accuracy. A wrong root, wrong node count, duplicate label pair, or out-of-range edge fails instead of producing a score.

For a public result, label all relevant dependencies without looking at Sentinel's predicted graph, version the labeling rules, record ambiguous cases, and publish the per-scenario counts and corpus denominator. Do not report the mini-agent's self-declared carrier edges as independent ground truth. The implementation and a worked arithmetic test are in [`provenance_eval.py`](../src/sentinel_replay/provenance_eval.py) and [`test_provenance_eval.py`](../tests/test_provenance_eval.py).
