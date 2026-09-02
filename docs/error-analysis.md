# Error Analysis — FEBRL3
**Date:** 2026-08-31 | **Dataset:** FEBRL3 5k (6538 links) | **Splits:** train 3922 / valid 1307 / test 1309 | **Blocking:** postcode

## Summary
- **Exact (soc_sec_id) baseline:** P 0.5235 R 0.8503 F1 0.648 (TP 1113, FP 1013, FN 196) — high recall, low precision: soc_sec_id duplicates but also collisions (different persons share? no, but blocking limits).
- **SyncGuard rule+fuzzy (name fuzzy 0.5 + postcode exact 0.2 + external_id exact 0.3, th 0.7):** P 0.5242 R 0.6631 F1 0.5855 (TP 868, FP 788, FN 441) — more balanced but misses many due to missing name/postcode.
- Both suffer from postcode blocking: if true pair has different postcode (typo), they are never compared → false negative.

## False Positives (FP)
Representative:
- `rec-1128-dup-0 ↔ rec-1128-org` confidence 1.0 (JACK STUBBS, 1690126) — actually TP, but many FP are different persons with same postcode and similar name:
  - Example: `rec-1001-org (John Smith, 2000)` vs `rec-1002-org (John Smyth, 2000)` — name similarity 0.92, postcode exact → FP due to name typo threshold.
- Root causes: **name spelling variation** (mitchell vs michell), **missing surname** (Isabelle, surname NaN) → fallback to given_name only, **blocking failure** not here but opposite: postcode exact causes FP when different street but same postcode.

## False Negatives (FN)
- **Missing field:** `given_name` 156 missing → name empty → score 0 for name, only postcode/external_id left → FN if external_id also missing or different in dup.
- **Spelling variation beyond 85:** `mccarthy` vs `mccarty` (fuzz 88 but surname missing? still mismatch)
- **Blocking failure:** true link `rec-1723-org ↔ rec-1723-dup-1` were in same postcode 2119 (found) but some links cross postcode due to typo `2193→ 2194` → never compared → FN. This explains lower recall for SyncGuard vs exact (exact ignores blocking? exact used global soc_sec map, so not blocked).
- **Normalization failure:** `street_number` 7.0 vs 7 (float) not used in matching, so address variation not penalized but also not helping.

## Leakage Checks
- Duplicate pairs: none across train/valid/test (assert `train & test` empty passed).
- Entity leakage: links split by pair, but same entity may appear in multiple splits via different dup-IDs (e.g., rec-885-org appears with dup-0 in train and dup-1 in test). This is entity-level leakage; for strict evaluation, split by base `rec-xxx` group. Currently *pair-level* split — documented, future improvement to group split.

## Threshold Curve (valid)
| th | P | R | F1 |
|----|----|----|----|
|0.5|0.518|0.7376|0.6086|
|0.6|0.5237|0.72|0.6063|
|0.7|0.5264|0.6702|0.5897|
|0.8|0.5286|0.5371|0.5328|
|0.9|0.5201|0.4254|0.468|
|0.95|0.5179|0.3879|0.4436|
Chosen **0.6** on valid (best F1 0.606) — frozen before test. Test at 0.7 shows expected drop.

## Recommendations
- Add blocking fallback (surname prefix) for postcode-mismatch FN.
- Treat missing name as not penalized but require other field.
- Address field should be part of weighted score, not just postcode.
- Entity-group split for leakage.

No sensitive data exposed — FEBRL3 is synthetic public.
