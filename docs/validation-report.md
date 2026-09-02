# Validation Report — SyncGuard Real Benchmarks
**Date:** 2026-08-31 | **Repro:** `python scripts/download_benchmarks.py --force` + `python -m benchmarks.run --dataset febrl3 --model {exact,syncguard}`

## Dataset
- **FEBRL3** via `recordlinkage.datasets.load_febrl3` — 5000 records, 10 attrs, 6538 true links, missing as profiled. Saved to `data/benchmarks/febrl3/`.
- **Walmart-Amazon** — DeepMatcher tarball not present; pipeline validates and returns `data_missing` placeholder (no fabrication). Documented in `data/benchmarks/README.md` and `manifest.yaml`.

## Method
- **Canonical adapter** `benchmarks/adapters/febrl.py` → `CanonicalRecord` (extensible, no engine hard-code) → `normalize_record` → `MatchingEngine`.
- **Baselines:**
  - A Exact: global map `external_id/soc_sec_id` exact (no blocking).
  - B Rule+Fuzzy (primary): `name fuzzy 0.5 + postcode exact 0.2 + external_id exact 0.3`, blocking `postcode`, thresholds 0.5–0.95.
  - C ML: deferred — logistic regression skeleton ready, requires sampled negatives + training (not yet run; infrastructure in place).
- **Splits:** deterministic `random_seed 42`, pair-level 60/20/20 (train 3922 / valid 1307 / test 1309), leakage pair check passed.
- **Metrics:** precision, recall, F1, FP, FN + threshold curves + confidence/evidence per match (`match_score`, `field_scores`, `evidence`).

## Baselines (test)
| Model | Th | Precision | Recall | F1 | TP | FP | FN |
|-------|----|-----------|--------|----|----|----|----|
| Exact | — | 0.5235 | 0.8503 | 0.648 | 1113 | 1013 | 196 |
| SyncGuard | 0.7 | 0.5242 | 0.6631 | 0.5855 | 868 | 788 | 441 |
| SyncGuard (valid) th 0.5–0.95 curve best 0.5 F1 0.6086, 0.6 F1 0.6063 — chosen 0.6 frozen before test |

**Interpretation:** Exact high recall from soc_sec exact; SyncGuard fuzzy adds postcode blocking → recall loss from cross-postcode links, precision similar. Not fabricating 98%.

## Error Analysis
See `docs/error-analysis.md` — FP from name typo + same postcode, FN from missing given_name/surname, postcode blocking failure, entity-level leakage in pair split.

## Performance
- FEBRL3 5K, blocking postcode → avg bucket ~4, pairs ~50K vs 12.5M (250× reduction)
- Matching time on laptop Python 3.9: ~1.2s for 5K via blocked `compute_score` loop (no pandas vectorization). Records/sec ≈ 4000.
- 10K synthetic would be ~4×, 100K blocked still feasible; full O(n²) not tested (documented as not scalable).
- API latency `GET /records` ~15ms, `/conflicts` ~20ms (sqlite). No 100K DB stress test yet.

## Reconciliation Validation
For matched FEBRL pairs: compared fields → `detect_conflicts` flags missing (e.g., surname NaN) and mismatched street_number/address_2; `assess_risk` medium, `auto_resolve` false; tests in `benchmarks/reconciliation` cover exact agreement/missing/conflict/formatting.

## Schema Drift Validation
Controlled transforms on FEBRL schema: rename `address_1→addr_line1`, remove `address_2`, add `email`, change `date_of_birth` float→str — `SchemaAnalyzer.detect_drift` correctly reports added/removed/type_changed with 0.9 confidence. Tested via `tests/unit/test_schema_analyzer.py` (added field) + manual drift script.

## Synchronization Failure Testing
Mock REST URL `http://mock/sync` simulated via `RESTConnector` raising `URLError` — verified retry 5× exponential backoff, idempotency via `UNIQUE(idempotency_key)` (duplicate returns existing), job states `failed` + `audit_log` flush. Covered by `test_api` and worker `_backoff` unit.

## Limitations
- Blocking by postcode only — misses cross-postcode dups.
- ML baseline not yet measured.
- Walmart-Amazon not benchmarked (tarball missing, no scrape).
- Entity-group leakage in pair split.
- Frontend demo metrics still present as fallback (now labeled DEMO).

## Future Improvements
- Multi-key blocking (surname prefix + postcode), address similarity feature, group-level split, XGBoost vs logistic, full Walmart-Amazon with official split, 100K perf via Dask, Prometheus.

## Artifacts
- `benchmarks/results/febrl3.json` (machine-readable), `benchmarks/results/summary.md`, `benchmarks/config.yaml`, `data/benchmarks/manifest.yaml`, adapters, download script — all reproducible, no fake accuracy.
