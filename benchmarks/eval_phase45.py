"""Phase 4.5 calibration: ML-only vs evidence-only vs combined (validation grid + frozen test)."""
import sys, json, random, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import logging
logging.disable(logging.CRITICAL)
from collections import defaultdict
from benchmarks.adapters.febrl import load_febrl_canonical, to_syncguard_dicts
from backend.app.services.normalization import normalize_record
from backend.app.services import model_service as ms
from backend.app.services import decision_engine as de
from backend.app.services import evidence_engine as ee

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
valid = set(lst[int(n * 0.6): int(n * 0.8)])
test = set(lst[int(n * 0.8):])
valid_recs = set(x for p in valid for x in p)
test_recs = set(x for p in test for x in p)

buckets = defaultdict(list)
for d in dicts:
    buckets[str(d.get("postcode") or "NA")].append(d["id"])

model = ms.load_model()


def eval_split(gold, recs):
    ml_scores, ev_dec, cb_dec, cb_conf = {}, {}, {}, {}
    y, s = [], []
    for ids in buckets.values():
        sids = sorted(i for i in ids if i in recs)
        for i in range(len(sids)):
            for j in range(i + 1, len(sids)):
                a, b = sids[i], sids[j]
                key = (a, b) if a < b else (b, a)
                feats = ms.featurize(idm[a], idm[b])
                prob = float(model.predict_proba([feats])[0][1])
                v = de.decide_pair(idm[a], idm[b], prob)
                ev = ee.build_evidence(idm[a], idm[b])
                es = ee.summarize(ev)
                evd = "MATCH" if (any(f["status"] == "EXACT_MATCH" and f.get("trusted_identifier") for f in ev["fields"]) or
                                  (any(f["field"] == "email" and f["status"] == "EXACT_MATCH" for f in ev["fields"]) and
                                   any(f["field"] == "phone" and f["status"] == "EXACT_MATCH" for f in ev["fields"]))) else (
                      "POSSIBLE_MATCH" if any(f["status"] in ("STRONG_MATCH", "EXACT_MATCH") for f in ev["fields"]) else "NO_MATCH")
                ml_scores[key] = prob
                ev_dec[key] = evd
                cb_dec[key] = v["decision"]
                cb_conf[key] = v["final_confidence"]
                if key in gold:
                    y.append(1)
                else:
                    y.append(0)
                s.append(prob)
    return ml_scores, ev_dec, cb_dec, cb_conf


def prf(pred, gold):
    tp, fp, fn = len(pred & gold), len(pred - gold), len(gold - pred)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"P": round(p, 4), "R": round(r, 4), "F1": round(2 * p * r / (p + r), 4) if p + r else 0.0, "tp": tp, "fp": fp, "fn": fn}


print("Evaluating validation...", flush=True)
ml_v, ev_v, cb_v, _ = eval_split(valid, valid_recs)
print("Evaluating test...", flush=True)
ml_t, ev_t, cb_t, cbc_t = eval_split(test, test_recs)

grid = []
for th in [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]:
    grid.append({"threshold": th, "combined": prf({k for k, v in ml_v.items() if v >= th and cb_v.get(k) == "MATCH"}, valid)})
print("GRID (combined MATCH@th on valid):")
for g in grid:
    print(g, flush=True)

from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
import numpy as np
pairs = sorted(ml_t.keys())

yt = [1 if k in test else 0 for k in pairs]
st = [ml_t[k] for k in pairs]
print(f"ROC-AUC={roc_auc_score(yt, st):.4f} PR-AUC={average_precision_score(yt, st):.4f} Brier={brier_score_loss(yt, st):.4f}", flush=True)
bins = defaultdict(lambda: [0, 0])
for k in pairs:
    b = min(9, int(ml_t[k] * 10))
    bins[b][0] += 1
    bins[b][1] += 1 if k in test else 0
print("RELIABILITY (bin: n, empirical rate):", {b: (v[0], round(v[1] / v[0], 3)) for b, v in sorted(bins.items())}, flush=True)

ml_test = prf({k for k, v in ml_t.items() if v >= 0.6}, test)
ev_test = prf({k for k, v in ev_t.items() if v == "MATCH"}, test)
cb_test = prf({k for k, v in cb_t.items() if v == "MATCH"}, test)
print("ML_ONLY:", ml_test, flush=True)
print("EVIDENCE_ONLY:", ev_test, flush=True)
print("COMBINED:", cb_test, flush=True)
cm = {"TP": cb_test["tp"], "FP": cb_test["fp"], "FN": cb_test["fn"]}
print("CONFUSION:", cm, flush=True)
(ROOT / "benchmarks" / "results" / "phase45_eval.json").write_text(json.dumps(
    {"grid": grid, "ml_only": ml_test, "evidence_only": ev_test, "combined": cb_test, "confusion": cm,
     "roc_auc": round(roc_auc_score(yt, st), 4), "pr_auc": round(average_precision_score(yt, st), 4),
     "brier": round(brier_score_loss(yt, st), 4)}, indent=2))
