# Matching Engine

## Stages

1. **Exact identifiers** — `customer_id`, `tax_id`, `email`, `phone` after normalization. Fast, high precision.
2. **Normalized comparison** — name/email/phone/address normalized then exact/fuzzy.
3. **Fuzzy** — RapidFuzz `fuzz.ratio` on name/address with configurable threshold (default 85).
4. **Weighted scoring** — `confidence = Σ(score_i * weight_i) / Σweights`; weights configurable (default name 0.4, email 0.3, phone 0.3). Every match retains `evidence` JSON.

## Classification (Phase 2 — model decisions)

```
prob ≥ MATCH_THRESHOLD (0.6)            → MATCH
prob ≥ POSSIBLE_MATCH_THRESHOLD (0.5)   → POSSIBLE_MATCH
else                                    → NO_MATCH (not persisted)
```
Thresholds in `core/config.py`, from validation (best F1 at 0.5–0.6, frozen on valid). Stored per match in `evidence.decision`. Legacy HIGH/MEDIUM/LOW labels predate Phase 2 and are superseded by decisions (risk tiers now live on conflicts).

## Explainability (Phase 2)

Per match: `confidence (=ml_prob, reproducible)`, `match_score`, `decision`, `model_version`, `field_scores{name,postcode,external_id,suburb,dob,token_overlap}` (actual model inputs), plus rule ticks `{field: {match, score, method, val_a, val_b}}`. Example: Quinlan Vexley pair → 99.89% MATCH, email ✗ (different), phone ✓, `field_scores` show name 1.0/token 1.0. UI shows WHY MATCHED from this data.

## Preventing False Matches

- Conservative address normalization (no aggressive abbreviation expansion).
- Email lowercased+trimmed only — no `+` nor `.` rewriting (unsafe).
- Blocking keys (email domain, phone prefix) to avoid O(n²) and spurious matches.
- Weights/thresholds tunable; high-risk conflicts never auto-resolved.

## Testing

`tests/unit/test_matching.py` covers exact/prefix/contains/fuzzy, evidence shape, scorer math.
