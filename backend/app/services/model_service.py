"""ModelService — single owner of trained artifact loading + inference (Phase 1).

Training (scripts/train_production_models.py) → pickle artifact.
Inference (MatchingEngine, live routes) → this service. No retraining here.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from backend.app.core.logging import logger

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
MODEL_ID = "syncguard_matcher"
MODEL_VERSION = "1.0.0"
FEATURE_VERSION = "1.0"
PREPROCESSING_VERSION = "1.0"
PRIMARY_ARTIFACT = "febrl3_ml.pkl"

_model_cache: Dict[str, Any] = {}
_metadata_cache: Optional[Dict[str, Any]] = None


def featurize(a: Dict[str, Any], b: Dict[str, Any]) -> List[float]:
    """Single canonical featurize — MUST match training (benchmarks/run.py)."""
    name_a = str(a.get("name") or a.get("given_name") or "")
    name_b = str(b.get("name") or b.get("given_name") or "")
    name_sim = fuzz.ratio(name_a, name_b) / 100 if name_a and name_b else 0.0
    pc_a = str(a.get("postcode") or (a.get("metadata") or {}).get("postcode") or "")
    pc_b = str(b.get("postcode") or (b.get("metadata") or {}).get("postcode") or "")
    pc_exact = 1.0 if pc_a and pc_a == pc_b else 0.0
    ext_a = str(a.get("external_id") or a.get("soc_sec_id") or a.get("phone") or "")
    ext_b = str(b.get("external_id") or b.get("soc_sec_id") or b.get("phone") or "")
    ext_exact = 1.0 if ext_a and ext_a == ext_b else 0.0
    suburb_a = str((a.get("metadata") or {}).get("suburb") or a.get("suburb") or "")
    suburb_b = str((b.get("metadata") or {}).get("suburb") or b.get("metadata", {}).get("suburb") if isinstance(b.get("metadata"), dict) else b.get("suburb") or "")
    suburb_b = str((b.get("metadata") or {}).get("suburb") or b.get("suburb") or "")
    suburb_sim = fuzz.ratio(suburb_a, suburb_b) / 100 if suburb_a and suburb_b else 0.0
    dob_a = str(a.get("date_of_birth") or "")
    dob_b = str(b.get("date_of_birth") or "")
    dob_exact = 1.0 if dob_a and dob_a == dob_b else 0.0
    token_overlap = len(set(name_a.lower().split()) & set(name_b.lower().split())) / max(1, len(set(name_a.lower().split()) | set(name_b.lower().split())))
    len_diff = abs(len(name_a) - len(name_b)) / max(1, max(len(name_a), len(name_b)))
    return [name_sim, pc_exact, ext_exact, suburb_sim, dob_exact, token_overlap, len_diff]


def artifact_path(name: str = PRIMARY_ARTIFACT) -> Path:
    return MODELS_DIR / name


def artifact_hash(name: str = PRIMARY_ARTIFACT) -> Optional[str]:
    p = artifact_path(name)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def load_model(name: str = PRIMARY_ARTIFACT):
    logger.info("MODEL_LOAD_STARTED", model_id=MODEL_ID, model_version=MODEL_VERSION, artifact=str(artifact_path(name)))
    if name in _model_cache:
        return _model_cache[name]
    import pickle
    p = artifact_path(name)
    if not p.exists():
        logger.error("MODEL_LOAD_FAILED", model_id=MODEL_ID, error="artifact missing")
        raise FileNotFoundError(f"Model artifact missing: {p}")
    try:
        with open(p, "rb") as f:
            model = pickle.load(f)
    except Exception as e:
        logger.error("MODEL_LOAD_FAILED", model_id=MODEL_ID, error=str(e))
        raise
    _model_cache[name] = model
    logger.info("MODEL_LOADED", model_id=MODEL_ID, model_version=MODEL_VERSION, artifact_hash=artifact_hash(name))
    return model


def get_model_version() -> str:
    return MODEL_VERSION


def get_model_metadata() -> Dict[str, Any]:
    global _metadata_cache
    if _metadata_cache is not None:
        return _metadata_cache
    metrics: Dict[str, Any] = {}
    for meta_file in ["febrl3_meta.json", "production_meta.json"]:
        p = MODELS_DIR / meta_file
        if p.exists():
            try:
                metrics[meta_file] = json.loads(p.read_text())
            except Exception:
                pass
    from backend.app.core.config import settings as _settings
    meta = {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "algorithm": "LogisticRegression(max_iter=300)",
        "match_threshold": _settings.MATCH_THRESHOLD,
        "possible_match_threshold": _settings.POSSIBLE_MATCH_THRESHOLD,
        "threshold_definitions": {
            "MATCH": f"score >= {_settings.MATCH_THRESHOLD}",
            "POSSIBLE_MATCH": f"score >= {_settings.POSSIBLE_MATCH_THRESHOLD} and score < {_settings.MATCH_THRESHOLD}",
            "NO_MATCH": f"score < {_settings.POSSIBLE_MATCH_THRESHOLD}",
        },
        "training_dataset": "febrl3-5k(6538 links)+walmart_amazon-10k+amazon_google-11k",
        "feature_version": FEATURE_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifact_path": str(artifact_path()),
        "artifact_hash": artifact_hash(),
        "status": "active" if artifact_path().exists() else "missing",
        "metrics": metrics,
    }
    _metadata_cache = meta
    return meta


def predict(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[float, List[float]]:
    model = load_model()
    feats = featurize(a, b)
    prob = float(model.predict_proba([feats])[0][1])
    return prob, feats


def decide(prob: float, match_threshold: Optional[float] = None, possible_threshold: Optional[float] = None) -> str:
    from backend.app.core.config import settings as _settings
    if match_threshold is None:
        match_threshold = _settings.MATCH_THRESHOLD
    if possible_threshold is None:
        possible_threshold = _settings.POSSIBLE_MATCH_THRESHOLD
    if prob >= match_threshold:
        return "MATCH"
    if prob >= possible_threshold:
        return "POSSIBLE_MATCH"
    return "NO_MATCH"


def predict_batch(pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> List[float]:
    model = load_model()
    feats = [featurize(a, b) for a, b in pairs]
    if not feats:
        return []
    probs = model.predict_proba(feats)[:, 1]
    return [float(p) for p in probs]
