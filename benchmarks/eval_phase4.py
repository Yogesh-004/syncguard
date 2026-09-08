"""Phase 4 model evaluation — blocked candidates, validation grid, frozen test report."""
import sys, json, random, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import logging
logging.disable(logging.CRITICAL)
from collections import defaultdict
import pandas as pd
from benchmarks.adapters.febrl import load_febrl_canonical, to_syncguard_dicts
from backend.app.services.normalization import normalize_record
from backend.app.services import model_service as ms

ROOT = pathlib.Path(__file__).resolve().parents[1]
records, links = load_febrl_canonical(str(ROOT / "data/benchmarks/febrl3/febrl3.csv"))
dicts = to_syncguard_dicts(records)
for d in dicts:
    nd = normalize_record(d)
    for k in ["name", "phone", "email"]:
        if k in nd:
            d[k] = nd[k]
idm = {d["id"]: d for d in dicts}
truth = set((a, b) if a < b else (b, a) for a, b in links)
lst = sorted(truth)
random.Random(42).shuffle(lst)
n = len(lst)
train = set(lst[: int(n * 0.6)])
valid = set(lst[int(n * 0.6): int(n * 0.8)])
test = set(lst[int(n * 0.8):])

buckets = defaultdict(list)
for d in dicts:
    buckets[str(d.get("postcode") or "NA")].append(d["id"])
cands = set()
for ids in buckets.values():
    ids_sorted = sorted(ids)
    for i in range(len(ids_sorted)):
        for j in range(i + 1, len(ids_sorted)):
            cands.add((ids_sorted[i], ids_sorted[j]))
print(f"candidates={len(cands)} full=12497500", flush=True)

model = ms.load_model()
t0 = time.time()
probs = {}
for a, b in cands:
    feats = ms.featurize(idm[a], idm[b])
    probs[(a, b)] = float(model.predict_proba([feats])[0][1])
print(f"inference {time.time()-t0:.1f}s", flush=True)


def prf(pred, gold):
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "tp": tp, "fp": fp, "fn": fn}


grid = []
for mt in [0.5, 0.6, 0.7, 0.8, 0.9]:
    for pt in [0.4, 0.5]:
        if pt >= mt:
            continue
        pred_m = {k for k, v in probs.items() if v >= mt}
        pred_p = {k for k, v in probs.items() if pt <= v < mt}
        grid.append({"match_th": mt, "possible_th": pt, "match": prf(pred_m, valid), "possible_recall": round(len(pred_p & valid) / len(valid), 4)})
print("VALIDATION GRID:")
for g in grid:
    print(g, flush=True)

final_m = {k for k, v in probs.items() if v >= 0.6}
final_p = {k for k, v in probs.items() if 0.5 <= v < 0.6}
out = {"dataset": "febrl3-blocked", "model": "syncguard_matcher v1.0.0", "split": "60/20/20 seed 42",
       "validation_grid": grid,
       "test": {"MATCH": prf(final_m, test),
                "POSSIBLE_MATCH": {"count": len(final_p & test), "recall": round(len(final_p & test) / len(test), 4)},
                "NO_MATCH_correct_rejections": len(test - final_m - final_p)},
       "note": "blocked candidates only (16115/12.5M); outside-block truth unrecoverable by design"}
(ROOT / "benchmarks" / "results" / "phase4_eval.json").write_text(json.dumps(out, indent=2))
print("TEST:", json.dumps(out["test"], indent=2), flush=True)
# FP/FN samples for error analysis (ids only)
fps = sorted(final_m - test)[:8]
fns = sorted(test - final_m - final_p)[:8]
print("FP_SAMPLE:", fps, flush=True)
print("FN_SAMPLE:", fns, flush=True)
