# Phase 4.6 Blocking Audit

## Current architecture
- **Live pipeline** (`api/routes.py` inline reconciliation): NO blocking — all O(n²) pairs within the source filter, hard-guarded by `MAX_JOB_RECORDS` (explicit error, no silent truncation). Candidate generation is exhaustive.
- **Benchmark scripts** (`benchmarks/run.py`, `eval_phase4.py`, `release_gate.py`): postcode grouping duplicated in each script (not shared) — same normalized `postcode` key, deterministic, no dedup issues (single pass).
- So benchmark and live do NOT share candidate logic: benchmark recall ceiling 0.763 is a measurement artifact of the eval harness, while live jobs never block at all (they hit the record cap instead). The suspected "blocker bottleneck" applies to benchmark methodology AND to any future large live jobs.

## Baseline (FEBRL3, complete truth, measured)
- Possible pairs: 12,497,500. Postcode candidates: 16,115 (775× reduction). True links: 6,538; entering matcher: 4,989 → candidate recall 0.763; lost before ML: 1,549. Within-candidate MATCH: P 1.0 / R 0.858. End-to-end recall ≈ 0.66. No duplicate candidates (single pass, set-based).

## Plan
Shared `services/blocking.py` (passes A–E + union + provenance + guardrails) used by BOTH a benchmark experiment script and (if accepted) the live pipeline. Thresholds/model untouched.
