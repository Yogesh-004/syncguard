# Conflict Data Model (Phase 2)

## Match (`matches`)
id, record_a/b FK (ordered a<b, deduped per job), confidence (=ml_prob, reproducible), match_method='ml', matched_fields[], evidence{decision MATCH/POSSIBLE_MATCH, match_score, model_version, job_id, field_scores{name,postcode,external_id,suburb,dob,token_overlap}, ml_features, rule ticks}, entity_group_id='job-{id}' (=job link), created_at. Source records never mutated — match is a relationship.

## Conflict (`conflicts`, one row per field)
id, job (via `match.entity_group_id`), match_id FK (always set, Phase 2), entity (record_a/b ids), source/target record ids + source_ids, field_name (single), source_value/target_value (original, immutable), recommended_value (recommendation), confidence (=match ml_prob), risk_level + risk_reason, reason (conflict_reason), status (`pending`=OPEN; Phase 3 states exist in column but Phase 2 creates only pending), created/updated_at.

## Relationships
`reconciliation_jobs --(entity_group_id=job-{id})--> matches --(match_id)--> conflicts`; `conflicts.record_a/b --> records`; `records.source_id --> sources`. Given conflict_id → match → job + model_version + both records. Given job → matches + conflicts (via `?job_id=`).

## Decisions
`MATCH` (prob ≥0.6 `MATCH_THRESHOLD`), `POSSIBLE_MATCH` (≥0.5), `NO_MATCH` (below; not persisted). Thresholds in `core/config.py`, from validation (best F1 at 0.5–0.6, frozen).
