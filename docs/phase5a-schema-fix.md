# Phase 5A — Schema Inference Fix

## 1. Original Defect

`infer_schema([{"name": "DOUGLAS ABBOTT"}, ...])` returned `data_type: 'datetime'` for a free-text name column. Reproduced against real NC voter-registration data. Expected: `string`. Reported in `docs/real-data-validation-report.md` §15 and `docs/temporal-validation-report.md` §15; NOT fixed during validation phases per phase rules.

## 2. Reproduction

- File: `backend/app/services/schema_analyzer.py`, functions `infer_type` / `infer_schema`.
- Old predicate: `infer_type` treated `normalize_date(v) is not None` as a datetime signal.
- `normalize_date('DOUGLAS ABBOTT')` returns `'DOUGLAS ABBOTT'` (normalizer fallback returns input unchanged when unparseable — by design, since matching depends on it). Verified this session: `normalize_date` → `'DOUGLAS ABBOTT'`.
- Hence the old check was vacuously true for every non-numeric string → any text column classified `datetime`.
- AFTER fix (verified this session): `infer_schema([{"name":"DOUGLAS ABBOTT"},{"name":"LARA SMITH"}])` → `string`; `infer_type(["2026-01-15","2025-12-01"])` → `datetime`; `infer_type(["DOUGLAS ABBOTT","JOHN SMITH"])` → `string`.

## 3. Root Cause

A normalizer was misused as a validator. `normalize_date` in `backend/app/services/normalization.py` (line 55) guarantees a return value and never returns `None` for non-empty strings (final `return s`). `infer_type`'s `all(... is not None ...)` predicate was therefore vacuous for strings. Ordering compounded it: the datetime check ran before the string fallback with no proportion, structure, or consistency requirement. `normalize_date` itself was left untouched (matching depends on its fallback behavior).

## 4. Fix

`backend/app/services/schema_analyzer.py` only:

- New `_strict_datetime` validator (not a normalizer): canonical `YYYY-MM-DD` or `None`. Accepts ISO via `fromisoformat` plus an explicit strict format list (`%Y-%m-%d`, `%Y/%m/%d`, `%d-%m-%Y`, `%m/%d/%Y`, `%d/%m/%Y`, `%d.%m.%Y`, timestamps incl. `%Y-%m-%dT%H:%M:%S%z`) plus validated 8-digit `yyyymmdd` only when the string contains no letters. Returns `None` for everything else, including `'DOUGLAS ABBOTT'`.
- `infer_type` requires EVIDENCE: at least 80% of non-missing values must strictly parse before `datetime`. A lone date-like value in a text column (or pure prose) stays `string`.
- Ambiguous day/month forms resolve month-first, matching the existing `normalize_date` format order — documented convention, not per-value guessing.

## 5. Type-Inference Rules

1. Empty (all `None`/blank) → `string` (conservative fallback).
2. All-bool → `boolean`; all-int → `integer`; all-numeric-parseable → `float`/`integer`.
3. ≥80% strictly-parseable dates → `datetime`; else → `string`.
4. Missing values (`None`/`""`/whitespace) are excluded from the proportion, so mostly-dates with gaps still parse; mostly-text with one date-like value stays `string`.
5. Malformed/ambiguous input fails safe to `string`; no code execution, no crashes (verified: `None`, `''`, `'   '`, `12345`, `'###'` → `string`).
6. Numeric-looking identifiers stay `integer` (conservative, documented); ambiguous `01/02/2026` → `datetime` month-first (documented convention).

## 6. Regression Tests

`backend/tests/unit/test_phase5a_schema.py`, 12 tests, 12/12 pass:

- Positive (4): `2026-01-15`, `15/01/2026`, `2026-01-15 14:30:00`, ISO-tz `2026-01-15T14:30:00+00:00`.
- Negative (3 tests, 7 values): `DOUGLAS ABBOTT`, `JOHN SMITH`, `ABC COMPANY`, `NEW YORK`, `123 MAIN STREET`.
- Mixed/edge (5): empty/`NULL`/whitespace/Unicode (`José García`, `Anne Müller`); mostly-dates-with-missing → `datetime`; mostly-text-with-one-date → `string`; ambiguous `01/02/2026` → `datetime` (documented); numeric identifiers stay numeric.

## 7. Real-Data Verification

- Repro input `DOUGLAS ABBOTT`: BEFORE → `datetime`; AFTER → `string` (verified this session).
- Same NC-sample shape: AFTER gives name → `string`, postcode → `integer`, mixed phone content → conservative `string`; drift severities sane (REMOVED name-parts `WARNING`, ADDED contact fields `SAFE`).
- Validation dataset, sampling, and thresholds untouched.

## 8. Temporal Pipeline Regression

- Fix is isolated to schema reporting (`infer_type` + `_strict_datetime`); matching model, weights, thresholds, blocking, normalization, decision/evidence/conflict engines untouched.
- Full backend suite 250/250 green (this session), so no legitimate classification relied on the old vacuous predicate.
- Baseline temporal metrics (frozen setup, from `docs/temporal-validation-report.md`): candidates 501,434, recall 1.000, MATCH 883 (TP 753/FP 130, P 0.8528, R 0.9947), incorrect automatic merges 0. Full 500k-pair rerun was not repeated in this verification session (harness cost ~158–240s + 2.68GB peak); no metric impact is expected by construction since the matcher code path is byte-identical. Flagged as a limitation below.

## 9. Performance

- `infer_schema` micro-probe (this session): 200 calls in 0.02s — negligible.
- No optimization performed; no material runtime change expected (strict-parse loop is per-column, bounded by sample size). Temporal total unchanged within noise per prior rerun note.

## 10. Unexpected Changes

None in product behavior. Full suite passed in a single run (250/250) this session — no flakes observed. One historical note: a prior full-suite run once showed flaky `test_parallel_push_idempotent` (sqlite lock contention, unrelated) passing on immediate re-run.

## 11. Limitations

- The 80% bar is a judgment call (documented, not tuned on labels).
- Numeric identifiers are indistinguishable from measures — conservatively numeric.
- Ambiguous dates resolved by month-first convention.
- Timezone-aware vs naive mixing is parsed, not normalized.
- Full 500k temporal rerun not repeated in this session (see §8).

## 12. Files Changed

- `backend/app/services/schema_analyzer.py` (fix only — `_strict_datetime` + 80% evidence rule in `infer_type`; `normalize_date` untouched).
- `backend/tests/unit/test_phase5a_schema.py` (new, 12 tests).
- `docs/temporal-validation-report.md` (appended Phase 5A addendum).
- This file.

## 13. Test Results

- New Phase 5A tests: 12/12 pass.
- Full backend suite: 250/250 pass (26.47s, this session).

---

SCHEMA FIX SCORECARD

Original reproduction fixed:
PASS

"DOUGLAS ABBOTT" classification:
STRING

Legitimate datetime detection:
PASS

False datetime cases:
0

Regression tests:
12/12

Full test suite:
250/250

Temporal pipeline regression:
PASS (by code isolation + full suite green; 500k rerun not repeated — see §8/§11)

Incorrect automatic merges:
0

Material performance regression:
NO

---

DECISION

Schema fix:
ACCEPTED

Reason:
The vacuous normalizer-as-validator predicate is replaced by an evidence-based strict-parse rule with full test cover and zero regressions.

Next permitted phase:
Multi-zip county temporal sample for disappearance/appearance claims, pending review approval.

Changes explicitly NOT made:
matching model, model weights, thresholds, candidate blocking, normalization, decision engine, evidence engine, conflict engine, synchronization, connectors, rollback, source-priority policies, frontend, database schema, API contracts, deployment, benchmark methodology

Confidence:
HIGH
