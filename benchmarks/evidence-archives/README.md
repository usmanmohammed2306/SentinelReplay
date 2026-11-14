# Reproducing the retained synthetic measurements

The final raw benchmark outputs are bundled here so the repository stays readable. Root-level JSON reports and measured source snapshots remain directly accessible under `benchmarks/results/`. The archives preserve original journal, checkpoint, query-index and per-candidate paths. They contain controlled synthetic data; no private operator environment or private signing/storage key is included.

`manifest.json` records each archive's SHA-256, file count and byte sizes. To restore one measurement's original paths, from the repository root:

```bash
shasum -a 256 benchmarks/evidence-archives/product-scale-final-2026-11-13.tar.gz
# Compare the digest with manifest.json before extracting the reviewed archive.
tar -xzf benchmarks/evidence-archives/product-scale-final-2026-11-13.tar.gz -C benchmarks/results
```

The example restores the50k capsule used by the deployment/HTTP probe. Repeat with another archive for raw policy-search resume or per-case inspection. The already published integrated demo capsule and small unit/browser fixtures need no extraction. Prior-attempt summary/source snapshots remain in Git; larger historical raw attempts remain local and are not silently relabeled as final results.

These are known synthetic fixtures, not independent provenance labels or unseen live-agent efficacy. The production release audit still reports its unresolved requirements.
