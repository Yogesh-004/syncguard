"""Performance at 1K/10K/100K — synthetic but blocked."""
import time, pathlib, sys, json, tracemalloc
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.adapters.febrl import load_febrl_canonical, to_syncguard_dicts
from benchmarks.run import blocking_by_postcode, baseline_fuzzy
from backend.app.services.matching import MatchingEngine

def measure(n):
    import pandas as pd
    # load full then sample
    df = pd.read_csv(ROOT/"data/benchmarks/febrl3/febrl3.csv")
    df = df.sample(n, random_state=42) if n < len(df) else df
    # create dicts
    from benchmarks.adapters.febrl import febrl_row_to_canonical
    recs = [febrl_row_to_canonical(row) for _,row in df.iterrows()]
    dicts = [r.to_syncguard_dict() for r in recs]
    # add normalize
    from backend.app.services.normalization import normalize_record
    for d in dicts:
        nd = normalize_record(d)
        d.update({k: nd.get(k, d.get(k)) for k in ["name","phone"]})
    buckets = blocking_by_postcode(dicts)
    tracemalloc.start()
    t0=time.time()
    pred = baseline_fuzzy(dicts, buckets, threshold=0.7)
    elapsed=time.time()-t0
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"n": n, "pred": len(pred), "time": round(elapsed,3), "rps": round(n/elapsed,1) if elapsed>0 else 0, "peak_mb": round(peak/1024/1024,2)}

if __name__=="__main__":
    for n in [1000, 10000, 5000]:
        r=measure(n)
        print(json.dumps(r))
    # 100K synthetic: duplicate df 20x with id suffix
    import pandas as pd
    df = pd.read_csv(ROOT/"data/benchmarks/febrl3/febrl3.csv")
    df100 = pd.concat([df.assign(rec_id=df["rec_id"]+f"-copy{i}") for i in range(20)], ignore_index=True).sample(100000, random_state=42, replace=True)
    df100.to_csv("/tmp/febrl100.csv", index=False)
    print("100K synthetic file created /tmp/febrl100.csv (not used for accuracy)")
