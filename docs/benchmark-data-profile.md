# Benchmark Data Profile
Generated 2026-08-31 via `scripts/download_benchmarks.py`

## FEBRL3 (recordlinkage.datasets.load_febrl3)
- **Rows:** 5000
- **Cols:** 11 (rec_id + 10 attributes)
- **Columns:** rec_id, given_name, surname, street_number, address_1, address_2, suburb, postcode, state, date_of_birth, soc_sec_id
- **Dtypes:** rec_id object, given_name object, surname object, street_number float64, address_1 object, address_2 object, suburb object, postcode int64, state object, date_of_birth float64 (yyyymmdd), soc_sec_id int64
- **Missing:** given_name 156, surname 79, street_number 245, address_1 154, address_2 693, suburb 85, state 85, date_of_birth 155, others 0
- **Duplicate rows:** 0
- **Unique rec_id:** 5000
- **Unique postcode:** 1273
- **Ground truth links:** 6538 pairs (MultiIndex rec_a–rec_b)
- **Class distribution:** 6538 positive links out of ~12.5M possible pairs (0.05% positive) — highly imbalanced; blocking required.
- **Blocking key:** postcode (reduces to ~buckets, avg bucket size ~4)
- **Splits (seed 42):** train 3922 / valid 1307 / test 1309 links

## Walmart-Amazon (DeepMatcher)
- **Status:** data_missing — official tarball not checked in (see `data/benchmarks/README.md`)
- **Expected:** train.csv, valid.csv, test.csv with `label` 0/1, fields left_title/right_title etc.
- **Provenance:** http://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data.tar.gz
- **Retrieval:** `scripts/download_benchmarks.py` validates presence, prints label distribution if present.
- **Ground truth:** label column; metrics same P/R/F1.

## Notes
- FEBRL3 is synthetic but structure mimics real linkage; missing values are intentional for error analysis.
- Adapter `benchmarks/adapters/febrl.py` maps given_name+surname→name, postcode→address.postcode, soc_sec_id→external_id/phone, preserves all in metadata.
- No hard-coded FEBRL logic in `services/matching.py`.
