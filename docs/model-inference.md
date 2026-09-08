# Model Inference (Phase 1)

## Model
- `syncguard_matcher v1.0.0`, `LogisticRegression(max_iter=300)`.
- Artifact: `backend/app/models/febrl3_ml.pkl` (sha `080455c6260f05a5`), plus product variants.
- Metadata: `backend/app/models/model_metadata.json` (+ live `GET /model/info`).
- Features v1.0 (7): name_sim, pc_exact, ext_exact, suburb_sim, dob_exact, token_overlap, len_diff.
- Preprocessing v1.0: `normalize_record` (upper/strip names, lower/trim email, digit phone) then `ModelService.featurize` — single canonical implementation used by both training (`benchmarks/run.py` aligned) and inference. No scaler object.
- Measured metrics (not fabricated): FEBRL3 P1.0/R0.76/F1 0.86; Walmart-Amazon P0.87/R0.52/F1 0.65; Amazon-Google P0.62/R0.25/F1 0.35.

## Training → inference
TRAIN: dataset → preprocessing → features → train → validate → evaluate → save artifact (+ hash).
INFERENCE: live CSV → same preprocessing → same `ModelService.featurize` → `load_model()` once (cached) → `predict`/`predict_batch` → confidence=ml_prob + rule evidence for ticks → persist.

## Service
`backend/app/services/model_service.py`: `load_model()`, `get_model_version()`, `get_model_metadata()`, `predict()`, `predict_batch()`. Logs `MODEL_LOAD_STARTED/LOADED/FAILED`. `MatchingEngine` delegates featurize+predict to it; `strict_ml=True` raises instead of rule fallback (live routes fail closed to FAILED/503).

## Run locally
`python scripts/train_production_models.py` (regenerates artifacts) → `curl http://127.0.0.1:8000/model/info`.
