# Audit (Phase 3)

## Events
CONFLICT_REVIEWED, RESOLUTION_CREATED, CONFLICT_DEFERRED, CONFLICT_REJECTED, DRY_RUN_STARTED, DRY_RUN_COMPLETED, PUSH_CONFIRMED, SYNC_STARTED, SYNC_SUCCEEDED, SYNC_FAILED, SYNC_RETRY, SYNC_VERIFIED. Each carries action/entity_type/entity_id/conflict+match+job refs/before-after/details/timestamp. No secrets stored (values limited to the conflicting field).

## Before/after
Source selection: before `{a,b}`, after `{resolved_value, selected_source}`. Manual edit: before `{a,b}`, after `{resolved_value: new}`.

## UI
Audit page (live `GET /audit-logs`, filter, click-for-detail) + per-conflict timeline (`GET /conflicts/{id}/audit`, chronological). All rows database-backed; verified live (9-event trail on conflict #133).
