# Benchmark Datasets — Provenance

## FEBRL3
- **Source:** `recordlinkage` Python package (`recordlinkage.datasets.load_febrl3`)
- **Task:** entity_resolution (deduplication, 5000 records, known duplicate links)
- **Retrieval:** `from recordlinkage.datasets import load_febrl3; df, true_links = load_febrl3(return_links=True)`
- **Ground truth:** true_links MultiIndex
- **License:** verify — synthetic data, recordlinkage is MIT, dataset itself needs_verification
- **Retrieval date:** 2026-08-31 (script generates)
- **Citation:** Christen, P. Febrl – Freely Extensible Biomedical Record Linkage. CMIS, 2008.
- **Local path:** `data/benchmarks/febrl3/febrl3.csv` and `links.csv` (generated, not committed if license unclear)
- **Redistribution:** store only metadata if unclear; script is reproducible.

## Walmart-Amazon
- **Source:** DeepMatcher (anhaidgroup/deepmatcher) — official tarball `http://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data.tar.gz`
- **Task:** entity_matching (labeled pairs, match 0/1)
- **Files:** `train.csv`, `valid.csv`, `test.csv` under `data/Walmart-Amazon/`
- **Ground truth:** `label` column
- **License:** needs_verification — research use, not redistributed; see DeepMatcher LICENSE (Apache 2.0 for code, data usage per original sources Walmart & Amazon)
- **Retrieval date:** 2026-08-31
- **Citation:** Mudgal et al. Deep Learning for Entity Matching: A Design Space Exploration. SIGMOD 2018.
- **Local path:** `data/benchmarks/walmart_amazon/` (empty until download; script prints URL and validates)
- **Official docs:** https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md

## Amazon-Google
- **Source:** DeepMatcher (same tarball)
- **Status:** deferred_until_first_two_pass
- **Local path:** `data/benchmarks/amazon_google/`

## Usage
```bash
python scripts/download_benchmarks.py           # febrl3 via package (offline-safe synthetic fallback)
python scripts/download_benchmarks.py --walmart # prints W-A download instructions (no scrape)
```

## Legal
Never commit raw W-A CSVs without verifying redistribution. The pipeline creates metadata and validates structure instead.
