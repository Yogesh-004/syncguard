"""Seed DB with benchmark datasets — connects benchmarks to every feature (Records, Matching, Conflicts, Jobs, Dashboard)."""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_local.db")
from backend.app.db.database import SessionLocal, Base, engine
from backend.app.db.models import SourceModel, RecordModel, MatchModel, ConflictModel, SchemaModel, ReconciliationJobModel, AuditLogModel
from backend.app.services.normalization import normalize_record
from backend.app.services.matching import MatchingEngine
from benchmarks.adapters.febrl import load_febrl_canonical
from benchmarks.adapters.walmart_amazon import load_product_pair_dataset

Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    # clear existing demo
    for m in [AuditLogModel, ConflictModel, MatchModel, RecordModel, SchemaModel, SourceModel, ReconciliationJobModel]:
        db.query(m).delete()
    db.commit()
    print("cleared old demo data")

    # FEBRL3 as primary benchmark source
    records, links = load_febrl_canonical(str(ROOT / "data/benchmarks/febrl3/febrl3.csv"))
    print(f"Loaded FEBRL3 {len(records)} records, {len(links)} links")

    # create benchmark sources
    febrl_src = SourceModel(name="FEBRL3 Benchmark", source_type="csv", config={"benchmark": "febrl3", "records": 5000})
    wa_src = SourceModel(name="Walmart-Amazon Benchmark", source_type="csv", config={"benchmark": "walmart_amazon", "pairs": 10242})
    ag_src = SourceModel(name="Amazon-Google Benchmark", source_type="csv", config={"benchmark": "amazon_google"})
    db.add_all([febrl_src, wa_src, ag_src])
    db.commit()
    db.refresh(febrl_src); db.refresh(wa_src); db.refresh(ag_src)
    print(f"sources FEBRL3={febrl_src.id} WA={wa_src.id} AG={ag_src.id}")

    # insert FEBRL3 records (use first 1000 for live demo to keep UI responsive, but mark total 5000)
    # For full connection, insert all 5000
    to_insert = records[:2000]  # 2000 for balance (full 5000 would be heavy for UI table)
    for r in to_insert:
        d = r.to_syncguard_dict()
        nd = normalize_record(d)
        # keep original metadata
        rec = RecordModel(source_id=febrl_src.id, source_record_id=r.entity_id, data=d, raw_data=r.metadata, normalized_data=nd)
        db.add(rec)
    db.commit()
    print(f"inserted {len(to_insert)} FEBRL3 records (sample of 5000, full available)")

    # insert Walmart-Amazon product pairs as records (sample 200)
    prod_data = load_product_pair_dataset(str(ROOT / "data/benchmarks/walmart_amazon"))
    if prod_data and "tableA" in prod_data:
        tableA = prod_data["tableA"]
        for _, row in tableA.head(100).iterrows():
            d = {"id": f"wa-A-{row['id']}", "title": row["title"], "brand": row.get("brand"), "category": row.get("category"), "price": row.get("price")}
            nd = normalize_record(d)
            rec = RecordModel(source_id=wa_src.id, source_record_id=f"wa-A-{row['id']}", data=d, raw_data=row.to_dict(), normalized_data=nd)
            db.add(rec)
        tableB = prod_data.get("tableB")
        if tableB is not None:
            for _, row in tableB.head(100).iterrows():
                d = {"id": f"wa-B-{row['id']}", "title": row["title"], "brand": row.get("brand"), "category": row.get("category"), "price": row.get("price")}
                nd = normalize_record(d)
                rec = RecordModel(source_id=wa_src.id, source_record_id=f"wa-B-{row['id']}", data=d, raw_data=row.to_dict(), normalized_data=nd)
                db.add(rec)
        db.commit()
        print("inserted 200 Walmart-Amazon product records")

    # create benchmark job
    total = db.query(RecordModel).count()
    job = ReconciliationJobModel(job_type="benchmark", source_id=str([febrl_src.id, wa_src.id]), status="completed", progress=100, total_records=5000, processed_records=total, idempotency_key="benchmark-seed-full", retry_count=0)
    db.add(job)
    db.commit()
    db.refresh(job)

    # run ML matching on the inserted FEBRL3 sample to create live matches/conflicts
    from backend.app.db.models import RecordModel as RM
    recs = db.query(RM).filter(RM.source_id == febrl_src.id).limit(500).all()
    dicts = []
    for r in recs:
        d = r.normalized_data or r.data or {}
        d = dict(d)
        d["id"] = r.id
        dicts.append(d)
    engine = MatchingEngine(use_ml=True)  # uses trained LogisticRegression
    matches = engine.find_matches(dicts, threshold=0.6)
    print(f"ML found {len(matches)} matches on sample 500")
    for m in matches[:50]:  # save first 50 to DB
        mm = MatchModel(record_a_id=m.record_a_id, record_b_id=m.record_b_id, confidence=m.confidence, match_method="ml", matched_fields=m.matched_fields, evidence=m.evidence, entity_group_id="benchmark")
        db.add(mm)
    db.flush()
    # create conflicts for high-confidence matches
    for m in matches[:20]:
        # find records
        ra = db.query(RM).filter(RM.id == m.record_a_id).first()
        rb = db.query(RM).filter(RM.id == m.record_b_id).first()
        if ra and rb:
            # detect field diff
            diff = []
            for k in set(list((ra.data or {}).keys()) + list((rb.data or {}).keys())):
                if (ra.data or {}).get(k) != (rb.data or {}).get(k):
                    diff.append({"field_name": k, "conflict_type": "mismatch", "values": {"a": (ra.data or {}).get(k), "b": (rb.data or {}).get(k)}, "sources": ["benchmark"]})
            if diff:
                cm = ConflictModel(record_a_id=m.record_a_id, record_b_id=m.record_b_id, match_id=None, confidence=m.confidence, conflicting_fields=diff[:2], evidence=m.evidence, risk_level="low" if m.confidence>0.8 else "medium", recommendation="AUTO-RESOLVE" if m.confidence>0.8 else "RECOMMEND", resolution_status="pending", auto_resolvable=m.confidence>0.8)
                db.add(cm)
    # schemas
    for src in [febrl_src, wa_src]:
        fields = [{"name": "title" if src==wa_src else "given_name", "data_type": "string"}]
        sm = SchemaModel(source_id=src.id, fields=[{"name": k, "data_type": "string"} for k in ["rec_id","given_name","surname","postcode","title","brand"]], field_count=6, version=1)
        db.add(sm)
    db.commit()
    # audit
    db.add(AuditLogModel(action="benchmark_seed", entity_type="benchmark", entity_id=str(job.id), details={"febrl3": len(to_insert), "walmart": 200, "matches": len(matches), "model": "LogisticRegression trained on all datasets"}))
    db.commit()
    print(f"Seed complete: {db.query(RecordModel).count()} records, {db.query(MatchModel).count()} matches, {db.query(ConflictModel).count()} conflicts, job {job.id}")
    print("Every feature now connected to benchmark — Records, Matching, Conflicts, Sources, Jobs all show benchmark data")
finally:
    db.close()
