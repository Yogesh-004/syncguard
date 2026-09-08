# Conflict Rules (Phase 2)

## Comparison (per field, normalization-aware)
Kinds: name (upper/strip), email (lower/trim), phone (digits/country), date (canonical YYYY-MM-DD), numeric (float+tolerance), address (token/case), identifier (alnum-lower exact), text (trim).
Outcomes: `NO_CONFLICT` (raw equal), `NORMALIZED_EQUAL` (equal after normalization → no conflict), `VALUE_CONFLICT`, `MISSING_VALUE` (one side empty), `BOTH_EMPTY` (no conflict).

## Null handling
`NULL vs value` → `MISSING_VALUE` (conflict, type `missing`), never equated with `value≠value`. Both empty → no conflict.

## Known limitation
`normalize_phone` assumes a 10-digit number is US (+1). A 10-digit Indian number without country code normalizes differently from its +91 form and WILL raise a conflict. Cross-country phone pairs should include country codes. (Found by test_10; documented, not silently fixed.)

## Risk
- `HIGH`: identifier field (email/phone/external_id/soc_sec_id) with `VALUE_CONFLICT`, or ≥3 conflicting fields on one entity.
- `MEDIUM`: `MISSING_VALUE`, or default non-critical conflict.
- `LOW`: match confidence ≥0.9 with non-critical disagreement.
Stored with `risk_reason` in evidence.

## Recommendation (conservative)
- One side missing → `SOURCE`/`TARGET` (the populated side) + reason.
- Both populated → `REVIEW REQUIRED` (no invented reliability scores).
- Legacy values `AUTO-RESOLVE`/`RECOMMEND` appear only on pre-Phase-2 rows.

## Status
New conflicts: `pending` (=OPEN). `approved/rejected/modified/deferred` are Phase 3 states; Phase 2 UI is review-only.
