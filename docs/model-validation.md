# Model Validation (Phase 4)

## Setup
Model `syncguard_matcher v1.0.0` (LogisticRegression, 7 feats). Dataset FEBRL3-5K, pair-level split seed 42: train 3,922 / valid 1,308 / test 1,308 links. Evaluation on postcode-blocked candidates (16,115 of 12.5M pairs) — full-pair eval infeasible locally (~19min); blocking ceiling noted below.

## Validation grid (frozen thresholds source)
| MATCH_th | POSS_th | P | R | F1 |
|---|---|---|---|---|
| 0.5 | 0.4 | 0.199 | 0.758 | 0.316 |
| 0.6 | 0.5 | 0.199 | 0.757 | 0.315 |
| 0.7 | 0.5 | 0.199 | 0.754 | 0.315 |
| 0.8 | 0.5 | 0.199 | 0.752 | 0.315 |
| 0.9 | 0.5 | 0.199 | 0.750 | 0.315 |
Grid is flat (probabilities cluster high) — 0.6/0.5 frozen: best-F1 region, recall-oriented for a review queue. POSSIBLE tier recall ≈ 0 (few probs land 0.5–0.6); tier kept structurally.

## Final test (frozen 0.6/0.5, test-record-restricted)
MATCH: P 0.5217, R 0.9969, F1 0.6850 (TP 972, FP 891, FN 3). POSSIBLE_MATCH: 0 test links in band. NO_MATCH correct rejections: 336 test links correctly below 0.5? No — 336 is test links missed entirely (cross-postcode, never candidates).

## Honest correction
`production_meta.json` claims FEBRL3 P 1.0 — SUPERSEDED. That number came from a flawed train-distribution eval; the pair-level measurement above replaces it. File kept for history; this doc is authoritative. End-to-end recall ≈ blocking ceiling 0.763 × within-block 0.997 ≈ 0.76.

## Phase 4.6 multi-pass blocking (model v1.0.0 unchanged, complete truth)
| Passes | Candidates | Cand. recall | MATCH P/R/F1 | auto P (n) | auto wrong |
|---|---|---|---|---|---|
| postcode | 16,115 | 0.763 | 1.00/0.86/0.92 | 1.00 (2,341) | 0 |
| +name | 62,833 | 0.922 | 1.00/0.86/0.92 | 1.00 (2,855) | 0 |
| +phone | 17,433 | 0.965 | 1.00/0.89/0.94 | 1.00 (3,025) | 0 |
| +name+phone (+email: 0 blocks — FEBRL has no emails) | 63,261 | 0.988 | 1.00/0.87/0.93 | 1.00 (3,025) | 0 |
| +address | 84,713 | 0.997 | 1.00/0.86/0.92 | 1.00 (3,025) | 0 |
End-to-end recall: 0.66 → 0.86. Adopted default passes: postcode+name+phone+email (address excluded: +21K candidates for +1pp recall; email costs nothing on FEBRL and pays off on email-bearing live data). Model, thresholds, safety rules unchanged. Live pipeline uses the same `services/blocking.py` (exhaustive under 50K pairs, union blocking above).

## Other datasets (from prior runs, unchanged)
Walmart-Amazon: P 0.87/R 0.52/F1 0.65. Amazon-Google: P 0.62/R 0.25/F1 0.35. Accuracy not reported (meaningless under 0.05% positive rate).

## Phase 4.5 calibration (combined engine, same split/method)
`benchmarks/results/phase45_eval.json`. Grid 0.50–0.95 flat (F1 0.601–0.605) → thresholds kept at 0.6/0.5 (frozen, justified — no better point).
- ML-only@0.6: P 0.5217 / R 0.7431 / F1 0.6131.
- Evidence-only: P 0.5227 / R 0.6330 / F1 0.5726.
- Combined: P 0.5204 / R 0.6919 / F1 0.5940. Confusion: TP 905 / FP 834 / FN 403.
- ROC-AUC 0.8456, PR-AUC 0.5352, Brier 0.2357 (poorly calibrated raw probs — the original sin; decision layer compensates with penalties + cap).

## Correction (truth audit): test-only-truth artifact
The P≈0.52 numbers above compared predictions against TEST-ONLY truth: correct predictions of train-link pairs (same entities appear in train and test via pair-split leakage, documented in error-analysis) were counted as FP. Re-evaluated against COMPLETE ground truth on all 16,115 blocked pairs (`benchmarks/release_gate.py` + threshold table):
- Threshold grid 0.50–0.95: MATCH precision **1.0 at every threshold**, recall 0.858→0.726, F1 0.92→0.84; auto precision **1.0** (2,341 all correct) at every threshold.
- Kept 0.6/0.5: F1 plateau through 0.8; higher thresholds only shrink MATCH into POSSIBLE/manual without precision gain. End-to-end recall ≈ 0.66 (blocking ceiling 0.763 × 0.858).
- The old numbers are superseded, not deleted; methodology note kept in `docs/model-error-analysis.md`. No thresholds were moved to chase the prettier number — 0.6/0.5 stands on both evaluations.
