"""Seed live demo data for SyncGuard - CRM/ERP/Accounting with realistic conflicts."""
import os, sys, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_local.db")
from backend.app.db.database import SessionLocal, Base, engine
from backend.app.db.models import SourceModel, RecordModel, MatchModel, ConflictModel, SchemaModel, ReconciliationJobModel, AuditLogModel
from backend.app.services.normalization import normalize_record
from backend.app.services.matching import MatchingEngine
from backend.app.services.reconciliation import ReconciliationEngine
from backend.app.services.schema_analyzer import SchemaAnalyzer
from datetime import datetime

Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    # clear
    for m in [AuditLogModel, ConflictModel, MatchModel, RecordModel, SchemaModel, SourceModel, ReconciliationJobModel]:
        db.query(m).delete()
    db.commit()

    # sources
    crm = SourceModel(name="CRM", source_type="csv", config={"system":"crm"})
    erp = SourceModel(name="ERP", source_type="csv", config={"system":"erp"})
    acct = SourceModel(name="Accounting", source_type="csv", config={"system":"accounting"})
    db.add_all([crm, erp, acct]); db.commit(); db.refresh(crm); db.refresh(erp); db.refresh(acct)
    print(f"sources {crm.id},{erp.id},{acct.id}")

    # core overlapping + unique records - spec example + 20 more synthetic
    base_customers = [
        {"customer_id":"C10482","name":"Ravi Kumar","email":"ravi@gmail.com","phone":"+91 9876543210","address":"MG Road, Bangalore","amount":5000},
        {"customer_id":"C10483","name":"Ananya Sharma","email":"ananya@demo.com","phone":"9876543211","address":"Connaught Place, Delhi","amount":7500},
        {"customer_id":"C10484","name":"Vikram Patel","email":"vikram@test.org","phone":"0091-9876543212","address":"Bandra, Mumbai","amount":3200},
    ]
    # CRM variations
    crm_records = [
        base_customers[0],
        base_customers[1],
        {"customer_id":"C10485","name":"Priya Singh","email":"priya@gmail.com","phone":"+91 9876543213","amount":4100},
    ]
    # ERP variations (normalized differently)
    erp_records = [
        {"customer_id":"10482","name":"RAVI KUMAR","email":"ravi@gmail.com","phone":"9876543210","address":"M G Road Bangalore","amount":5000},
        {"customer_id":"10483","name":"Ananya  Sharma","email":"ANANYA@DEMO.COM","phone":"+91-9876543211","address":"Connaught Place Delhi","amount":7500},
        {"customer_id":"10486","name":"Arjun Mehta","email":"arjun@example.com","phone":"9876543214","amount":6200},
    ]
    # Accounting variations (missing, abbreviated, drift)
    acct_records = [
        {"customer_id":"C-10482","name":"Ravi K.","email":"ravi@gmail.com","phone":None,"address":"MG Road","transaction_amount":5000},
        {"customer_id":"C-10483","name":"Ananya Sharma","email":"ananya@demo.com","phone":"9876543211","amount":7500},
        {"customer_id":"C-10487","name":"Sneha Reddy","email":"sneha@sample.io","phone":"9876543215","amount":8800},
    ]

    all_sources = [(crm, crm_records), (erp, erp_records), (acct, acct_records)]
    record_objs = []
    for src, recs in all_sources:
        for r in recs:
            rec = RecordModel(source_id=src.id, source_record_id=r["customer_id"], data=r, raw_data=r, normalized_data=normalize_record(r))
            db.add(rec); record_objs.append(rec)
    # add 20 random unique to reach volume
    for i in range(20):
        src = random.choice([crm, erp, acct])
        name = random.choice(["John","Alice","Bob"]) + " " + random.choice(["Smith","Jones","Brown"])
        r = {"customer_id":f"R{i:04d}","name":name,"email":f"{name.lower().replace(' ','.')}{i}@example.com","phone":f"555{random.randint(100000,999999)}","amount":round(random.uniform(100,9000),2)}
        rec = RecordModel(source_id=src.id, source_record_id=r["customer_id"], data=r, raw_data=r, normalized_data=normalize_record(r))
        db.add(rec); record_objs.append(rec)
    db.commit()
    print(f"inserted {len(record_objs)} records")

    # schemas
    for src in [crm, erp, acct]:
        fields = [{"name":k,"data_type":"string"} for k in ["customer_id","name","email","phone","amount"]]
        if src == acct:
            fields = [{"name":k,"data_type":"string"} for k in ["customer_id","name","email","phone","transaction_amount"]]
        sm = SchemaModel(source_id=src.id, fields=fields, field_count=len(fields), version=1)
        db.add(sm)
    db.commit()

    # build matching using normalized data
    db_records = db.query(RecordModel).all()
    # prepare dict list for matching
    dicts = [{"id": r.id, "name": r.normalized_data.get("name") if r.normalized_data else r.data.get("name"), "email": r.normalized_data.get("email") if r.normalized_data else r.data.get("email"), "phone": r.normalized_data.get("phone") if r.normalized_data else r.data.get("phone")} for r in db_records]
    # add raw filtering for missing phone -> use normalized phone may be ""
    engine_match = MatchingEngine()
    matches = engine_match.find_matches(dicts, threshold=0.7)
    print(f"matches found raw {len(matches)}")
    # also use ReconciliationEngine to generate conflicts
    rec_engine = ReconciliationEngine()
    # create a simple conflict detection between CRM and ERP/Accounting for demo: manually create conflicts for high confidence pairs
    # Use the reconciliation engine on dicts
    result = rec_engine.run_reconciliation([r.data for r in db_records])
    print(f"reconciliation result {result}")

    # Persist matches/conflicts - create explicit example for Ravi
    ravi_crm = db.query(RecordModel).filter(RecordModel.source_id==crm.id, RecordModel.source_record_id=="C10482").first()
    ravi_erp = db.query(RecordModel).filter(RecordModel.source_id==erp.id, RecordModel.source_record_id=="10482").first()
    ravi_acct = db.query(RecordModel).filter(RecordModel.source_id==acct.id, RecordModel.source_record_id=="C-10482").first()
    if ravi_crm and ravi_erp:
        m = MatchModel(record_a_id=ravi_crm.id, record_b_id=ravi_erp.id, confidence=0.967, match_method="weighted", matched_fields=["email","phone","name"], evidence={"email":{"match":True,"score":1.0},"phone":{"match":True,"score":1.0},"name":{"match":True,"score":0.94}}, entity_group_id="g-ravi")
        db.add(m); db.flush()
        c = ConflictModel(record_a_id=ravi_crm.id, record_b_id=ravi_erp.id, match_id=m.id, confidence=0.967, conflicting_fields=[{"field":"customer_id","values":{"crm":"C10482","erp":"10482"},"type":"mismatch"}], evidence={"name_similarity":0.94}, risk_level="low", recommendation="AUTO-RESOLVE", resolution_status="pending", auto_resolvable=True)
        db.add(c)
    if ravi_crm and ravi_acct:
        m2 = MatchModel(record_a_id=ravi_crm.id, record_b_id=ravi_acct.id, confidence=0.92, match_method="weighted", matched_fields=["email","name"], evidence={"email":{"match":True},"phone":{"match":False,"reason":"missing_field"},"name":{"match":True,"score":0.88}}, entity_group_id="g-ravi")
        db.add(m2); db.flush()
        c2 = ConflictModel(record_a_id=ravi_crm.id, record_b_id=ravi_acct.id, match_id=m2.id, confidence=0.92, conflicting_fields=[{"field":"phone","values":{"crm":"+919876543210","accounting":None},"type":"missing"},{"field":"name","values":{"crm":"Ravi Kumar","accounting":"Ravi K."},"type":"mismatch"}], evidence={"phone_missing":True}, risk_level="medium", recommendation="RECOMMEND", resolution_status="pending", auto_resolvable=False)
        db.add(c2)
    if ravi_erp and ravi_acct:
        m3 = MatchModel(record_a_id=ravi_erp.id, record_b_id=ravi_acct.id, confidence=0.91, match_method="weighted", matched_fields=["email"], evidence={}, entity_group_id="g-ravi")
        db.add(m3); db.flush()
        c3 = ConflictModel(record_a_id=ravi_erp.id, record_b_id=ravi_acct.id, match_id=m3.id, confidence=0.91, conflicting_fields=[{"field":"customer_id","values":{"erp":"10482","accounting":"C-10482"},"type":"mismatch"}], evidence={}, risk_level="medium", recommendation="RECOMMEND", resolution_status="pending")
        db.add(c3)

    # add a couple random conflicts
    for rec in db_records[:2]:
        pass

    # jobs
    job = ReconciliationJobModel(job_type="reconciliation", source_id=str([crm.id, erp.id, acct.id]), status="completed", progress=100, total_records=len(db_records), processed_records=len(db_records), idempotency_key="seed-live-1", retry_count=0)
    db.add(job)
    sync = __import__("backend.app.db.models", fromlist=["SyncJobModel"]).SyncJobModel(reconciliation_job_id=1, source_id=str(crm.id), target_source_id=str(erp.id), status="failed", error_message="HTTP 500", idempotency_key="SYNC-18291")
    # need to flush job first
    db.flush()
    # fix fk
    from backend.app.db.models import SyncJobModel
    sj = SyncJobModel(reconciliation_job_id=job.id, source_id=str(crm.id), target_source_id=str(erp.id), status="failed", error_message="HTTP 500", idempotency_key="SYNC-18291-seed")
    db.add(sj)

    db.add(AuditLogModel(action="seed", entity_type="system", entity_id="seed", details={"records": len(record_objs), "matches": 3, "conflicts": 3}))

    db.commit()
    print(f"seed done: records {db.query(RecordModel).count()} matches {db.query(MatchModel).count()} conflicts {db.query(ConflictModel).count()} jobs {db.query(ReconciliationJobModel).count()} schemas {db.query(SchemaModel).count()}")

finally:
    db.close()
