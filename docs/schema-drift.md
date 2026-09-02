# Schema Drift Detection

## Detection

On each ingest, hash `fields` (column names + inferred dtypes via Pandas) and compare to `schemas` latest version for that `source_id`.

Detect:
- **added / removed** columns — set diff.
- **renamed** — RapidFuzz on removed vs added names; if score > 85 and types compatible → `{from: "amount", to: "transaction_amount", confidence: 0.94}`.
- **type changed** — same name, dtype differs.

## Storage

`schemas` table: `source_id FK, fields JSON, version INT` with UNIQUE(source_id, version). Comparison endpoint `GET /schemas/drift` returns `{removed, added, renamed_suggestions[], type_changes[], affected_pipelines, requires_approval}`.

## UX

Schema tab shows Current vs Previous side-by-side, highlights added (green)/removed (red)/renamed (amber). Auto-migration gated behind `requires_approval`.

## Example

```
SCHEMA DRIFT DETECTED
Removed: amount
Added: transaction_amount
Potential rename: amount → transaction_amount (94%)
Affected pipelines: 3 — REQUIRES APPROVAL
```
