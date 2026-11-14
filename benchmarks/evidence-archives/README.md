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


The November 14 current-source hardening evidence is separately indexed in [sentinel-hardening-manifest-2026-11-13.json](sentinel-hardening-manifest-2026-11-13.json). Its five `sentinel-hardening-*` archives restore paths under `production-hardening-2026-11-13/`. They omit generated Git hook templates, private key files and caches; normalize tar uid/gid/owner metadata; and preserve included file bytes. The original archives above remain unchanged. The directory date identifies the cohort, while execution receipts record actual UTC timestamps. Full release remains gated.

The recording-budget amendment has its own [November 14 archive manifest](sentinel-recording-manifest-2026-11-14.json). Six `sentinel-recording-*` archives retain the current demo, scale, corpus and 25-pair recording measurements, the distinct pre-adoption 25-pair repeat, and the initial scale permission failure. They restore paths under `recording-qualification-2026-11-14/`. The fresh p95 miss and original relative-overhead failures remain visible; changing the criterion does not turn them into passes. Historical search data stays in its original archive.
