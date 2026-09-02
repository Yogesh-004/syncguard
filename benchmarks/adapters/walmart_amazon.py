"""Walmart-Amazon → Canonical (product) adapter — DeepMatcher structured."""
import pandas as pd
import pathlib
from typing import Dict, List, Tuple
from .base import CanonicalRecord

def load_product_pair_dataset(base_dir: str) -> Dict[str, pd.DataFrame]:
    p = pathlib.Path(base_dir)
    # find train/valid/test either at root or exp_data
    for sub in ["", "exp_data"]:
        cand = p / sub / "train.csv" if sub else p / "train.csv"
        if cand.exists():
            base = p / sub if sub else p
            break
    else:
        return {}
    out = {}
    for split in ["train", "valid", "test"]:
        f = base / f"{split}.csv"
        if f.exists():
            out[split] = pd.read_csv(f)
    # also load tables
    for t in ["tableA", "tableB"]:
        f = base / f"{t}.csv"
        if not f.exists():
            f = p / f"{t}.csv"
        if f.exists():
            out[t] = pd.read_csv(f)
    return out

def product_featurize(left: pd.Series, right: pd.Series) -> List[float]:
    from rapidfuzz import fuzz
    title_a = str(left.get("title") or "")
    title_b = str(right.get("title") or "")
    title_sim = fuzz.ratio(title_a.lower(), title_b.lower()) / 100 if title_a and title_b else 0
    brand_a = str(left.get("brand") or "").lower().strip()
    brand_b = str(right.get("brand") or "").lower().strip()
    brand_exact = 1.0 if brand_a and brand_a == brand_b else 0.0
    cat_a = str(left.get("category") or "").lower().strip()
    cat_b = str(right.get("category") or "").lower().strip()
    cat_exact = 1.0 if cat_a and cat_a == cat_b else 0.0
    # price diff normalized
    try:
        pa = float(str(left.get("price") or "").replace("$","").strip() or 0)
        pb = float(str(right.get("price") or "").replace("$","").strip() or 0)
        price_sim = 1 - min(1, abs(pa-pb)/ max(1, max(pa,pb))) if pa and pb else 0
    except:
        price_sim = 0
    model_a = str(left.get("modelno") or left.get("manufacturer") or "").lower()
    model_b = str(right.get("modelno") or right.get("manufacturer") or "").lower()
    model_exact = 1.0 if model_a and model_a == model_b else 0.0
    token_overlap = len(set(title_a.lower().split()) & set(title_b.lower().split())) / max(1, len(set(title_a.lower().split()) | set(title_b.lower().split())))
    return [title_sim, brand_exact, cat_exact, price_sim, model_exact, token_overlap]

def to_canonical_pair(left: pd.Series, right: pd.Series, label: int) -> CanonicalRecord:
    # create a combined canonical for UI
    name = f"{left.get('title','')[:60]} | {right.get('title','')[:60]}"
    return CanonicalRecord(entity_id=f"{left.get('id')}-{right.get('id')}", source="walmart_amazon", name=name, metadata={"label": label, "left": left.to_dict(), "right": right.to_dict()})
