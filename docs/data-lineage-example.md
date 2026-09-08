# Data Lineage Example (live, Phase 4 e2e)

Record `live-0` (Quinn Avery) traced end-to-end (IDs, values minimal):

- source: #16 (`Live: phase4_e2e.csv`, live:true)
- record: #2295 (`live-0`) and #2296 (`live-1`)
- analysis job: #16 (mode live, model v1.0.0, 2 records, completed)
- model: syncguard_matcher v1.0.0 (`febrl3_ml.pkl` hash 080455c6260f05a5)
- match: #293 (confidence 0.9989, decision MATCH, job 16)
- conflict: #134 (field email, match_id 293, HIGH, REVIEW REQUIRED, pending→modified)
- resolution: #22 (MANUAL_EDIT → `quinn.avery@fixed.com`, previous preserved)
- sync job: #4 (MOCK destination, UPDATE email, SUCCESS, verified true, attempt 1)
- audit: 8 events (REVIEWED → RESOLUTION_CREATED → DRY_RUN ×2 → PUSH_CONFIRMED → SYNC_STARTED → SUCCEEDED → VERIFIED)

Verified via `GET /conflicts/134` (full chain) and `GET /conflicts/134/audit` after backend restart (persistence proven).
