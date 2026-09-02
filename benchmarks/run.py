"""Benchmark runner — python -m benchmarks.run --dataset febrl3 --model syncguard"""
import argparse, json, pathlib, random, itertools
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT))
from benchmarks.adapters.febrl import load_febrl_canonical, to_syncguard_dicts
from benchmarks.evaluate import compute_metrics
from backend.app.services.matching import MatchingEngine
from backend.app.services.normalization import normalize_record

def load_febrl():
    records, links = load_febrl_canonical(str(ROOT / "data" / "benchmarks" / "febrl3" / "febrl3.csv"))
    # normalize via syncguard
    dicts = to_syncguard_dicts(records)
    # also normalize name/email/phone via engine's expected fields
    for d in dicts:
        nd = normalize_record(d)
        d.update({k: nd.get(k, d.get(k)) for k in ["name","phone","email"]})
        # keep rec_id as id
    truth = set((a,b) if a<b else (b,a) for a,b in links)
    return dicts, truth

def blocking_by_postcode(dicts):
    buckets = defaultdict(list)
    for d in dicts:
        pc = str(d.get("postcode") or d.get("metadata",{}).get("postcode") or d.get("address",{}).get("postcode") or "NA")
        buckets[pc].append(d)
    return buckets

def baseline_exact(dicts, buckets=None):
    # exact on soc_sec_id / external_id
    pred=set()
    # build map external_id -> ids
    m=defaultdict(list)
    for d in dicts:
        eid = str(d.get("external_id") or d.get("soc_sec_id") or d.get("phone") or "")
        if eid and eid!="None":
            m[eid].append(d["id"])
    for ids in m.values():
        for a,b in itertools.combinations(ids,2):
            pred.add((a,b) if a<b else (b,a))
    return pred

def baseline_fuzzy(dicts, buckets, threshold=0.7):
    pred=set()
    engine2 = MatchingEngine(rules=[
        {"field_name":"name","match_type":"fuzzy","weight":0.5,"threshold":85},
        {"field_name":"postcode","match_type":"exact","weight":0.2},
        {"field_name":"external_id","match_type":"exact","weight":0.3},
    ])
    for _, bucket in buckets.items():
        for i in range(len(bucket)):
            for j in range(i+1, len(bucket)):
                conf, _, _ = engine2.compute_score(bucket[i], bucket[j])
                if conf >= threshold:
                    a,b = bucket[i]["id"], bucket[j]["id"]
                    pred.add((a,b) if a<b else (b,a))
    return pred

def featurize(a: dict, b: dict):
    from rapidfuzz import fuzz
    name_a = str(a.get("name") or "")
    name_b = str(b.get("name") or "")
    name_sim = fuzz.ratio(name_a, name_b) / 100 if name_a and name_b else 0.0
    pc_a = str(a.get("postcode") or a.get("metadata",{}).get("postcode") or "")
    pc_b = str(b.get("postcode") or b.get("metadata",{}).get("postcode") or "")
    pc_exact = 1.0 if pc_a and pc_a == pc_b else 0.0
    ext_a = str(a.get("external_id") or "")
    ext_b = str(b.get("external_id") or "")
    ext_exact = 1.0 if ext_a and ext_a == ext_b else 0.0
    suburb_a = str(a.get("address",{}).get("city") or a.get("metadata",{}).get("suburb") or "")
    suburb_b = str(b.get("address",{}).get("city") or b.get("metadata",{}).get("suburb") or "")
    suburb_sim = fuzz.ratio(suburb_a, suburb_b) / 100 if suburb_a and suburb_b else 0.0
    dob_a = str(a.get("date_of_birth") or "")
    dob_b = str(b.get("date_of_birth") or "")
    dob_exact = 1.0 if dob_a and dob_a == dob_b else 0.0
    token_overlap = len(set(name_a.lower().split()) & set(name_b.lower().split())) / max(1, len(set(name_a.lower().split()) | set(name_b.lower().split())))
    len_diff = abs(len(name_a) - len(name_b)) / max(1, max(len(name_a), len(name_b)))
    return [name_sim, pc_exact, ext_exact, suburb_sim, dob_exact, token_overlap, len_diff]

def split_truth(truth, seed=42):
    lst = sorted(truth)
    random.Random(seed).shuffle(lst)
    n=len(lst); n_train=int(n*0.6); n_valid=int(n*0.2)
    return set(lst[:n_train]), set(lst[n_train:n_train+n_valid]), set(lst[n_train+n_valid:])

def run_febrl3(model="exact", threshold=0.7):
    dicts, truth = load_febrl()
    buckets = blocking_by_postcode(dicts)
    train_truth, valid_truth, test_truth = split_truth(truth, seed=42)
    # leakage check
    assert not (train_truth & test_truth), "leakage"
    # For metrics, evaluate only test portion but pred is global — filter pred to test entity ids
    test_ids = set(x for p in test_truth for x in p)
    # restrict pred to pairs where both in test_ids to avoid penalizing train pairs
    if model=="exact":
        pred = baseline_exact(dicts, buckets)
    elif model=="syncguard":
        pred = baseline_fuzzy(dicts, buckets, threshold=threshold)
    elif model=="fuzzy":
        pred = baseline_fuzzy(dicts, buckets, threshold=threshold)
    else:
        pred=set()
    # ML baseline
    if model=="ml":
        # train simple logistic on train pairs
        from sklearn.linear_model import LogisticRegression
        import numpy as np
        # build id->dict map
        idm = {d["id"]: d for d in dicts}
        # positive train
        X_train = []
        y_train = []
        for a,b in train_truth:
            if a in idm and b in idm:
                X_train.append(featurize(idm[a], idm[b]))
                y_train.append(1)
        # sample negatives within buckets (same size as positives)
        neg_needed = len(X_train)
        negs = []
        for _, bucket in buckets.items():
            for i in range(len(bucket)):
                for j in range(i+1, len(bucket)):
                    a,b = bucket[i]["id"], bucket[j]["id"]
                    key = (a,b) if a<b else (b,a)
                    if key not in truth:
                        negs.append((a,b))
                        if len(negs) >= neg_needed*2:
                            break
                if len(negs) >= neg_needed*2:
                    break
            if len(negs) >= neg_needed*2:
                break
        random.Random(42).shuffle(negs)
        for a,b in negs[:neg_needed]:
            if a in idm and b in idm:
                X_train.append(featurize(idm[a], idm[b]))
                y_train.append(0)
        clf = LogisticRegression(max_iter=200)
        clf.fit(np.array(X_train), np.array(y_train))
        # predict on test via threshold 0.5 on buckets
        pred=set()
        for _, bucket in buckets.items():
            for i in range(len(bucket)):
                for j in range(i+1, len(bucket)):
                    a,b = bucket[i]["id"], bucket[j]["id"]
                    feats = featurize(bucket[i], bucket[j])
                    prob = float(clf.predict_proba([feats])[0][1])
                    if prob >= 0.5:
                        pred.add((a,b) if a<b else (b,a))
        # set pred for outer
    # filter to test
    pred_test = set(p for p in pred if p[0] in test_ids and p[1] in test_ids)
    metrics = compute_metrics(pred_test, test_truth)
    # threshold curve on valid
    curve=[]
    if model=="syncguard":
        for th in [0.5,0.6,0.7,0.8,0.9,0.95]:
            p = baseline_fuzzy(dicts, buckets, threshold=th)
            # use valid for selection but report test here for simplicity
            valid_ids = set(x for p in valid_truth for x in p)
            p_valid = set(x for x in p if x[0] in valid_ids and x[1] in valid_ids)
            m = compute_metrics(p_valid, valid_truth)
            curve.append({"threshold": th, **m})
    # explainability sample
    sample = []
    if pred_test:
        for a,b in list(pred_test)[:3]:
            da = next(d for d in dicts if d["id"]==a)
            db = next(d for d in dicts if d["id"]==b)
            eng = MatchingEngine()
            conf, fields, ev = eng.compute_score(da, db)
            sample.append({"a":a,"b":b,"confidence":conf,"evidence":ev,"decision":"match" if conf>=threshold else "non-match"})
    ml_info = {}
    if model=="ml":
        ml_info = {"model":"LogisticRegression","features":["name_sim","pc_exact","ext_exact","suburb_sim","dob_exact","token_overlap","len_diff"]}
    return {"dataset":"febrl3","model":model,"threshold":threshold,"test_metrics":metrics,"curve":curve,"sample":sample, "truth_counts":{"train":len(train_truth),"valid":len(valid_truth),"test":len(test_truth)}, **ml_info}

def run_product(dataset="walmart_amazon", model="syncguard", threshold=0.7):
    import pathlib, pandas as pd
    from benchmarks.adapters.walmart_amazon import load_product_pair_dataset, product_featurize
    from benchmarks.evaluate import compute_metrics
    base = ROOT / "data" / "benchmarks" / dataset
    data = load_product_pair_dataset(str(base))
    if not data or "train" not in data or data["train"] is None or data["train"].empty:
        return {"dataset":dataset,"model":model,"status":"data_missing","metrics":{"precision":0,"recall":0,"f1":0},"note":"Download from http://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/"+dataset}
    # load tables
    tableA = data.get("tableA")
    tableB = data.get("tableB")
    if tableA is None or tableB is None:
        # try exp_data
        for sub in ["exp_data"]:
            if (base / sub / "tableA.csv").exists():
                tableA = pd.read_csv(base / sub / "tableA.csv")
                tableB = pd.read_csv(base / sub / "tableB.csv")
                break
    if tableA is None or tableB is None:
        return {"dataset":dataset,"model":model,"status":"data_missing","metrics":{"precision":0,"recall":0,"f1":0}}
    tableA = tableA.set_index("id")
    tableB = tableB.set_index("id")
    def pairs_to_features(df):
        feats=[]
        labels=[]
        pairs=[]
        for _,row in df.iterrows():
            try:
                lid = int(row["ltable_id"]); rid = int(row["rtable_id"]); lab = int(row["label"])
            except:
                continue
            if lid not in tableA.index or rid not in tableB.index:
                continue
            left = tableA.loc[lid]; right = tableB.loc[rid]
            feats.append(product_featurize(left, right))
            labels.append(lab)
            pairs.append(((lid, rid), lab))
        return feats, labels, pairs
    train_df = data.get("train")
    valid_df = data.get("valid")
    test_df = data.get("test")
    # train ML
    if model=="ml":
        from sklearn.linear_model import LogisticRegression
        import numpy as np
        X_train, y_train, _ = pairs_to_features(train_df)
        if not X_train:
            return {"dataset":dataset,"model":model,"metrics":{"precision":0,"recall":0,"f1":0}}
        clf = LogisticRegression(max_iter=300)
        clf.fit(np.array(X_train), np.array(y_train))
        # evaluate on test
        X_test, y_test, pairs = pairs_to_features(test_df)
        probs = clf.predict_proba(np.array(X_test))[:,1]
        pred = set()
        truth = set()
        for (pair, lab), prob in zip(pairs, probs):
            if prob >= 0.5:
                pred.add(pair)
            if lab==1:
                truth.add(pair)
        m = compute_metrics(pred, truth)
        # sample explainability
        sample=[]
        for (pair, lab), prob, feat in zip(pairs[:3], probs[:3], X_test[:3]):
            sample.append({"pair": pair, "prob": round(float(prob),3), "features": feat, "label": lab, "decision": "match" if prob>=0.5 else "non-match"})
        return {"dataset":dataset,"model":"LogisticRegression","threshold":0.5,"test_metrics":m,"metrics":m,"features":["title_sim","brand_exact","cat_exact","price_sim","model_exact","token_overlap"],"sample":sample, "train_size": len(X_train), "test_size": len(X_test)}
    else:
        # syncguard rule: title fuzzy 0.85 + brand exact
        from rapidfuzz import fuzz
        X_test, y_test, pairs = pairs_to_features(test_df)
        pred=set(); truth=set()
        for (pair, lab), feat in zip(pairs, X_test):
            title_sim = feat[0]
            brand_exact = feat[1]
            # simple rule: title_sim >=0.8 and brand_exact or title_sim >=0.9
            is_match = (title_sim >= 0.8 and brand_exact==1) or title_sim >= 0.9 or (title_sim >= 0.7 and feat[5] >= 0.5)
            if is_match:
                pred.add(pair)
            if lab==1:
                truth.add(pair)
        m = compute_metrics(pred, truth)
        return {"dataset":dataset,"model":"syncguard_rule","threshold":threshold,"test_metrics":m,"metrics":m, "sample": [{"pair": p, "decision": "match" if p in pred else "non-match"} for p in list(pred)[:3]]}

def run_walmart(model="syncguard"):
    return run_product("walmart_amazon", model=model)

def run_amazon_google(model="syncguard"):
    return run_product("amazon_google", model=model)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["febrl3","walmart_amazon","amazon_google"], default="febrl3")
    ap.add_argument("--model", choices=["exact","syncguard","fuzzy","ml"], default="syncguard")
    ap.add_argument("--threshold", type=float, default=0.7)
    args = ap.parse_args()
    if args.dataset=="febrl3":
        res = run_febrl3(model=args.model if args.model!="syncguard" else "syncguard", threshold=args.threshold)
    elif args.dataset=="walmart_amazon":
        res = run_product("walmart_amazon", model=args.model, threshold=args.threshold)
    elif args.dataset=="amazon_google":
        res = run_product("amazon_google", model=args.model, threshold=args.threshold)
    else:
        res = run_walmart(model=args.model)
    outdir = ROOT / "benchmarks" / "results"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{args.dataset}.json"
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    # also summary.md
    summ = outdir / "summary.md"
    summ.write_text(f"# Benchmark Summary\n\nLast run {args.dataset} {args.model} threshold {args.threshold}\n\n```json\n{json.dumps(res, indent=2)}\n```\n")

if __name__=="__main__":
    main()
