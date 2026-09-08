# Conflict Resolution (Phase 3)

## Lifecycle
`pending`(OPEN) → first action logs REVIEWED → `approved/modified`(RESOLVED) | `rejected`(RESOLVED-rejected, terminal, non-pushable) | `deferred`(DEFERRED, stays in queue). Re-resolving a terminal conflict → 409; identical repeat → idempotent 200 with note. Map: `docs/phase3-audit.md`.

## Actions
USE_SOURCE_A / USE_SOURCE_B (approve alias → A), MANUAL_EDIT (modify alias, field-type validated: email/phone/date/numeric via normalization utils), REJECT, DEFER (+optional reason). One resolution per conflict row in `resolution_logs`; structured payload in `detail` JSON: canonical, selected_source, previous_value, resolved_value, originals, reason. Original `conflicting_fields` never mutated.

## Endpoints
`POST /conflicts/{id}/resolve`, `GET /conflicts/{id}/resolutions`, `POST /resolutions/{id}/dry-run`, `POST /resolutions/{id}/push {confirm:true}`, `GET /sync-jobs/{id}`, `POST /sync-jobs/{id}/retry`, `GET /conflicts/{id}/audit`.
