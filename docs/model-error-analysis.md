# Model Error Analysis (Phase 4, record IDs only — no PII)

## False positives (blocked test eval, FP=891)
Dominant: LOW-INFORMATION RECORDS — same postcode + similar suburb/DOB with missing given_name/surname (e.g. `rec-8-dup-0` vs `rec-1496-org`: name_sim 0.22 yet prob 0.65 via suburb match). Secondary: AMBIGUOUS ENTITY — common names same postcode (e.g. multiple `McCarthy` variants). Model overweighting suburb_sim is the MODEL ERROR component.

## False negatives (FN=3 within-block; ~336 cross-postcode)
Dominant: BLOCKING FAILURE — true links spanning postcodes (typo'd postcodes) never become candidates (e.g. `rec-1009-dup-2`/`rec-1009-org` family). Within-block FNs: SPELLING VARIATION beyond fuzzy tolerance + MISSING FIELD combos.

## Threshold errors
None material — grid flat; 0.6/0.5 sits at the F1 plateau. Lowering to 0.5 adds +1 TP for +2 FP on validation: not justified.

## Conflicting identifier
soc_sec exact-match feature dominates positives; when identifiers collide across entities (data entry reuse) the model cannot distinguish — needs human review (hence MEDIUM/HIGH risk routing).

## What would actually help
Multi-key blocking (surname-prefix OR postcode) to recover cross-postcode links without 775× loss; suburb feature down-weighting; both require re-validation — not implemented (Phase 4 hardens, doesn't retrain).
