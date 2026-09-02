# Matching Engine

## Stages

1. **Exact identifiers** — `customer_id`, `tax_id`, `email`, `phone` after normalization. Fast, high precision.
2. **Normalized comparison** — name/email/phone/address normalized then exact/fuzzy.
3. **Fuzzy** — RapidFuzz `fuzz.ratio` on name/address with configurable threshold (default 85).
4. **Weighted scoring** — `confidence = Σ(score_i * weight_i) / Σweights`; weights configurable (default name 0.4, email 0.3, phone 0.3). Every match retains `evidence` JSON.

## Classification

```
>0.95  HIGH   → auto-resolvable candidate (still audit-logged)
0.80–0.95 MEDIUM → recommend / manual approval
<0.80  LOW    → manual review
no match → UNMATCHED
```
Thresholds configurable per job.

## Explainability

Per match:
```
confidence, matched_fields[], evidence{field: {match, score, method, val_a, val_b}}
```
UI shows ✓/⚠ per field, risk, recommendation.

## Preventing False Matches

- Conservative address normalization (no aggressive abbreviation expansion).
- Email lowercased+trimmed only — no `+` nor `.` rewriting (unsafe).
- Blocking keys (email domain, phone prefix) to avoid O(n²) and spurious matches.
- Weights/thresholds tunable; high-risk conflicts never auto-resolved.

## Testing

`tests/unit/test_matching.py` covers exact/prefix/contains/fuzzy, evidence shape, scorer math.
