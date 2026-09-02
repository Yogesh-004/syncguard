#!/usr/bin/env python
"""Reproducible benchmark dataset pipeline — FEBRL3 via recordlinkage + Walmart-Amazon placeholder."""
import argparse, os, sys, json, hashlib, pathlib
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
FEBRL_DIR = ROOT / "data" / "benchmarks" / "febrl3"
WA_DIR = ROOT / "data" / "benchmarks" / "walmart_amazon"

def ensure_dirs():
    FEBRL_DIR.mkdir(parents=True, exist_ok=True)
    WA_DIR.mkdir(parents=True, exist_ok=True)

def download_febrl3(force=False):
    out_csv = FEBRL_DIR / "febrl3.csv"
    out_links = FEBRL_DIR / "links.csv"
    out_meta = FEBRL_DIR / "meta.json"
    if out_csv.exists() and out_links.exists() and not force:
        print(f"[febrl3] exists — skip (use --force to re-download) {out_csv}")
        return out_csv
    try:
        from recordlinkage.datasets import load_febrl3
        df, links = load_febrl3(return_links=True)
        print(f"[febrl3] loaded df shape {df.shape}, links {len(links)}")
        df_reset = df.reset_index()
        df_reset.to_csv(out_csv, index=False)
        import pandas as pd
        links_df = pd.DataFrame(links.tolist(), columns=["rec_a","rec_b"])
        links_df.to_csv(out_links, index=False)
        meta = {
            "dataset": "febrl3",
            "source": "recordlinkage.datasets.load_febrl3",
            "rows": int(df.shape[0]),
            "cols": int(df.shape[1]),
            "columns": list(df.columns),
            "links": int(len(links)),
            "generated_at": datetime.utcnow().isoformat(),
            "csv": str(out_csv.relative_to(ROOT)),
            "links_csv": str(out_links.relative_to(ROOT)),
        }
        # stats
        print(f"[febrl3] columns {list(df.columns)}")
        print(f"[febrl3] missing\n{df.isnull().sum().to_dict()}")
        out_meta.write_text(json.dumps(meta, indent=2))
        print(f"[febrl3] saved {out_csv} ({out_csv.stat().st_size} bytes)")
        return out_csv
    except Exception as e:
        print(f"[febrl3] load failed: {e}", file=sys.stderr)
        # synthetic fallback to keep pipeline reproducible offline
        import pandas as pd, numpy as np
        print("[febrl3] generating synthetic fallback (offline) — NOT real FEBRL3", file=sys.stderr)
        np.random.seed(42)
        n=500
        df = pd.DataFrame({
            "rec_id": [f"rec-{i}" for i in range(n)],
            "given_name": np.random.choice(["John","Jane","Alice","Bob","Charlie"], n),
            "surname": np.random.choice(["Smith","Jones","Brown","Wilson"], n),
            "street_number": np.random.randint(1,100,n),
            "address_1": np.random.choice(["Main St","High St","Park Ave"], n),
            "suburb": np.random.choice(["North","South","East"], n),
            "postcode": np.random.choice(["2000","3000","4000"], n),
            "state": np.random.choice(["NSW","VIC"], n),
            "date_of_birth": pd.date_range("1950-01-01","2000-01-01", periods=n).astype(str),
            "soc_sec_id": [f"{np.random.randint(100000,999999)}" for _ in range(n)],
        })
        df.to_csv(out_csv, index=False)
        links_like = pd.DataFrame({"a":[0,1],"b":[2,3]})
        links_like.to_csv(out_links, index=False)
        meta = {"dataset":"febrl3_synthetic_fallback","rows":n,"cols":len(df.columns),"columns":list(df.columns),"links":2,"generated_at":datetime.utcnow().isoformat()}
        out_meta.write_text(json.dumps(meta, indent=2))
        return out_csv

def walmart_instructions():
    meta = WA_DIR / "meta.json"
    readme = ROOT / "data" / "benchmarks" / "README.md"
    info = {
        "dataset": "walmart_amazon",
        "official_urls": ["http://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data.tar.gz","https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md"],
        "local_path": str(WA_DIR.relative_to(ROOT)),
        "expected_files": ["train.csv","valid.csv","test.csv"],
        "ground_truth": "label column (1=match)",
        "license": "needs_verification",
        "retrieval_date": datetime.utcnow().isoformat(),
        "instructions": "Download tarball, extract Walmart-Amazon folder to data/benchmarks/walmart_amazon/. Do not commit raw CSVs without license check.",
    }
    WA_DIR.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps(info, indent=2))
    has_files = all((WA_DIR / f).exists() for f in info["expected_files"])
    if has_files:
        print(f"[walmart_amazon] files present in {WA_DIR}")
        # validate
        import pandas as pd
        for f in info["expected_files"]:
            p = WA_DIR / f
            df = pd.read_csv(p, nrows=5)
            print(f"  {f}: cols {list(df.columns)[:6]} rows {len(pd.read_csv(p))} label_dist {pd.read_csv(p)['label'].value_counts().to_dict() if 'label' in df.columns else 'no label'}")
    else:
        print("[walmart_amazon] NOT present — manual download required:")
        print("  wget http://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data.tar.gz")
        print(f"  tar -xzf deepmatcher_data.tar.gz -C {WA_DIR.parent}  # yields data/Walmart-Amazon/")
        print(f"  cp {WA_DIR.parent}/Walmart-Amazon/*.csv {WA_DIR}/")
    return not has_files

def main():
    ap = argparse.ArgumentParser(description="SyncGuard benchmark dataset pipeline")
    ap.add_argument("--force", action="store_true", help="force redownload")
    ap.add_argument("--walmart", action="store_true", help="check walmart-amazon instructions")
    args = ap.parse_args()
    ensure_dirs()
    download_febrl3(force=args.force)
    walmart_instructions()
    # summary stats if available
    try:
        import pandas as pd
        f = FEBRL_DIR / "febrl3.csv"
        if f.exists():
            df = pd.read_csv(f)
            print(f"\n[febrl3 stats] rows={len(df)} cols={len(df.columns)} columns={list(df.columns)}")
            print(f"  dtypes: {df.dtypes.to_dict()}")
            print(f"  missing: {df.isnull().sum().to_dict()}")
            print(f"  dup rows: {df.duplicated().sum()}")
            if "rec_id" in df.columns:
                print(f"  unique rec_id: {df['rec_id'].nunique()}")
    except Exception as e:
        print(f"stats error {e}")

if __name__ == "__main__":
    main()
