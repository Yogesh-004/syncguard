"""Release gate: auto-resolution safety on FEBRL ground truth (blocked candidates)."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import logging
logging.disable(logging.CRITICAL)
from collections import defaultdict
from benchmarks.adapters.febrl import load_febrl_canonical, to_syncguard_dicts
from backend.app.services.normalization import normalize_record
from backend.app.services import model_service as ms
from backend.app.services import decision_engine as de

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
buckets = defaultdict(list)
for d in dicts:
    buckets[str(d.get("postcode") or "NA")].append(d["id"])

model = ms.load_model()
total = m_match = m_poss = m_no = 0
auto_total = auto_correct = auto_wrong = 0
blockers = []
crit_auto = 0
for ids in buckets.values():
    s = sorted(ids)
    for i in range(len(s)):
        for j in range(i + 1, len(s)):
            a, b = s[i], s[j]
            key = (a, b) if a < b else (b, a)
            feats = ms.featurize(idm[a], idm[b])
            prob = float(model.predict_proba([feats])[0][1])
            v = de.decide_pair(idm[a], idm[b], prob)
            total += 1
            if v["decision"] == "MATCH":
                m_match += 1
            elif v["decision"] == "POSSIBLE_MATCH":
                m_poss += 1
            else:
                m_no += 1
            if v["auto_resolvable"]:
                auto_total += 1
                if key in truth:
                    auto_correct += 1
                else:
                    auto_wrong += 1
                    if v["decision"] == "MATCH" and v["risk"] == "LOW":
                        blockers.append({"pair": key, "confidence": v["final_confidence"]})
            # critical contradiction auto-resolved?
            summ_crit = any(f.get("trusted_identifier") and f["status"] == "MISMATCH" for f in v["field_evidence"]["fields"])
            if summ_crit and v["auto_resolvable"]:
                crit_auto += 1

prec = auto_correct / auto_total if auto_total else 0.0
rec = auto_correct / len(truth) if truth else 0.0
out = {"candidate_pairs": total, "MATCH": m_match, "POSSIBLE_MATCH": m_poss, "NO_MATCH": m_no,
       "auto_total": auto_total, "auto_correct": auto_correct, "auto_wrong": auto_wrong,
       "auto_precision": round(prec, 4), "auto_recall": round(rec, 4),
       "match_low_safe_incorrect": len(blockers), "blocker_samples": blockers[:5],
       "critical_contradiction_auto": crit_auto,
       "verdict": "RELEASE BLOCKED" if (blockers or crit_auto) else "RELEASE CANDIDATE"}
print(json.dumps(out, indent=2))
(ROOT / "benchmarks" / "results" / "release_gate.json").write_text(json.dumps(out, indent=2))
