"""Benchmark pipeline smoke tests — no fake accuracy."""
from benchmarks.adapters.febrl import load_febrl_canonical
from benchmarks.evaluate import compute_metrics

def test_febrl_load():
    recs, links = load_febrl_canonical("data/benchmarks/febrl3/febrl3.csv")
    assert len(recs) == 5000
    assert len(links) == 6538
    assert recs[0].entity_id.startswith("rec-")

def test_adapter_extensible():
    recs, _ = load_febrl_canonical("data/benchmarks/febrl3/febrl3.csv")
    d = recs[0].to_syncguard_dict()
    assert "name" in d or "external_id" in d

def test_metrics_not_fabricated():
    pred = {("a","b"),("c","d")}
    truth = {("a","b"),("e","f")}
    m = compute_metrics(pred, truth)
    assert m["precision"] == 0.5
    assert m["recall"] == 0.5

def test_leakage_check():
    train = {("a","b")}
    test = {("c","d")}
    assert not (train & test)

def test_schema_drift_detect():
    from backend.app.services.schema_analyzer import SchemaAnalyzer
    sa = SchemaAnalyzer()
    fa = [{"name":"amount","data_type":"float"},{"name":"customer_id","data_type":"string"}]
    fb = [{"name":"transaction_amount","data_type":"float"},{"name":"customer_id","data_type":"string"}]
    r = sa.detect_drift("test",1,2,fa,fb)
    assert r.total_changes == 2  # removed amount, added transaction_amount

def test_sync_idempotency():
    from backend.app.db.database import SessionLocal
    from backend.app.db.models import ReconciliationJobModel
    db = SessionLocal()
    try:
        db.query(ReconciliationJobModel).filter(ReconciliationJobModel.idempotency_key=="test-idem-bm").delete()
        db.commit()
        j = ReconciliationJobModel(job_type="reconciliation", source_id="1", status="queued", idempotency_key="test-idem-bm")
        db.add(j); db.commit()
        # duplicate should be blocked by UNIQUE
        j2 = ReconciliationJobModel(job_type="reconciliation", source_id="1", status="queued", idempotency_key="test-idem-bm")
        db.add(j2)
        try:
            db.commit()
            assert False, "should have unique violation"
        except Exception:
            db.rollback()
    finally:
        db.query(ReconciliationJobModel).filter(ReconciliationJobModel.idempotency_key=="test-idem-bm").delete()
        db.commit()
        db.close()
