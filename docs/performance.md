# Performance (measured, Phase 4)

## Matching baseline (O(n²), per-pair sklearn `predict_proba`)
Measured 2026-09-06, FEBRL-style records, threshold 0.6, laptop dev machine:
| n | pairs | matches | time | per-pair | records/s |
|---|-------|---------|------|----------|-----------|
| 200 | 19,900 | 80 | 1.84s | 0.093ms | 109 |
| 500 | 124,750 | 592 | 11.48s | 0.092ms | 44 |
| 1,000 | 499,500 | — | ~46s (extrapolated) | — | — |
| 5,000 | 12,497,500 | — | ~19min (extrapolated) | — | — |
| 10,000 | ~50M | — | ~77min (extrapolated) | — | — |

1K/5K full runs were NOT executed (120s+ timeouts observed); larger rows are linear extrapolation from the stable 0.092ms/pair rate. Memory: pairs stream, no pair matrix — dicts dominate (~1KB/record; 50K ≈ 50MB est, not measured → NOT TESTED beyond 500).

## Blocking evaluation
Postcode blocking on FEBRL3-5K: 16,115 candidates vs 12,497,500 full (775× reduction, inference 1.3s). BUT blocking recall ceiling = 0.763 (1,549/6,538 true links span postcodes) — a 24% recall loss. Decision: NOT implemented in live path (correctness over speed); documented here with numbers.

## 500-record cap → MAX_JOB_RECORDS
Cap exists because of quadratic runtime (500 ≈ 11s inline; 2000 ≈ 3min). Now configurable (`MAX_JOB_RECORDS`, default 2000) with explicit 500-error when exceeded — no silent truncation (before: silent `limit(500)`). Live jobs measured: 2–4 records instant; benchmark seed jobs complete.

## Bottleneck
Per-pair `predict_proba` Python overhead dominates, not I/O. Future (not implemented): vectorized batch predict + multi-key blocking with recall guard.
