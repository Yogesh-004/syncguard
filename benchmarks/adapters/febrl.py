"""FEBRL3 → Canonical adapter. No logic in matching engine."""
import pandas as pd
from typing import List, Tuple
from .base import CanonicalRecord

def febrl_row_to_canonical(row: pd.Series) -> CanonicalRecord:
    rec_id = str(row.get("rec_id") or row.name)
    given = str(row.get("given_name") or "").strip()
    surname = str(row.get("surname") or "").strip()
    name = f"{given} {surname}".strip() if given or surname else None
    # address dict
    addr = {}
    if pd.notna(row.get("street_number")): addr["street_number"] = str(row["street_number"])
    if pd.notna(row.get("address_1")): addr["street"] = str(row["address_1"])
    if pd.notna(row.get("address_2")): addr["line2"] = str(row["address_2"])
    if pd.notna(row.get("suburb")): addr["city"] = str(row["suburb"])
    if pd.notna(row.get("postcode")): addr["postcode"] = str(row["postcode"])
    if pd.notna(row.get("state")): addr["state"] = str(row["state"])
    dob = str(row.get("date_of_birth")) if pd.notna(row.get("date_of_birth")) else None
    if dob and dob != "nan":
        # format yyyymmdd -> keep as is for normalization
        pass
    else:
        dob = None
    external_id = str(row.get("soc_sec_id")) if pd.notna(row.get("soc_sec_id")) else None
    # metadata keeps all original
    meta = {k: (None if pd.isna(v) else v) for k,v in row.to_dict().items()}
    return CanonicalRecord(
        entity_id=rec_id,
        source="febrl3",
        name=name,
        phone=external_id,  # use soc_sec as phone-like identifier for exact test (also external_id)
        address=addr if addr else None,
        date_of_birth=dob,
        external_id=external_id,
        metadata=meta,
    )

def load_febrl_canonical(csv_path: str) -> Tuple[List[CanonicalRecord], List[Tuple[str,str]]]:
    df = pd.read_csv(csv_path, dtype=str)
    # also load links
    import pathlib
    p = pathlib.Path(csv_path).parent / "links.csv"
    links=[]
    if p.exists():
        ldf = pd.read_csv(p, dtype=str)
        if "rec_a" in ldf.columns:
            links = list(zip(ldf["rec_a"], ldf["rec_b"]))
        else:
            # fallback
            links = [tuple(x) for x in ldf.values.tolist()]
    records = [febrl_row_to_canonical(row) for _,row in df.iterrows()]
    return records, links

def to_syncguard_dicts(records: List[CanonicalRecord]) -> List[dict]:
    return [r.to_syncguard_dict() for r in records]
