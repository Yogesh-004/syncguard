# Reconciliation

## Flow

`records (normalized)` → pairwise `MatchingEngine` → `matches` → `conflicts` detection.

## Conflict Detection

For each matched pair, compare fields across systems:
- different name/phone/email/address/amount/status
- missing values, inconsistent timestamps, conflicting identifiers
Represented as `conflicts.conflicting_fields = [{field, val_a, val_b, type}]` + `evidence`.

## Resolution

| Action | When |
|--------|------|
| auto-resolve | confidence >95 and `auto_resolvable=true` and low risk → still creates audit row |
| recommend | 80–95 → UI shows "Approve/Reject/Modify/Defer" |
| human review | <80 or high-risk → must not auto-resolve |

Every resolution inserts `resolution_logs` + updates `conflicts.resolution_status` + `audit_logs` in one TX; never silent overwrite.

## Audit

`audit_logs` stores who/what/when/prev/new; queryable by `request_id`, `job_id`, `entity_type`.
