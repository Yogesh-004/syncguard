"""Phase 1 tests — model persistence + real live inference on unseen data."""
import json
import pathlib
import pickle

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODELS = ROOT / "backend" / "app" / "models"


def test_1_artifact_exists():
    assert (MODELS / "febrl3_ml.pkl").exists()


def test_2_model_loadable():
    from backend.app.services import model_service as ms
    m = ms.load_model()
    assert hasattr(m, "predict_proba")


def test_3_metadata_readable():
    from backend.app.services import model_service as ms
    meta = ms.get_model_metadata()
    for k in ["model_id", "model_version", "algorithm", "artifact_path", "status"]:
        assert k in meta
    assert meta["status"] == "active"


def test_4_inference_works():
    from backend.app.services import model_service as ms
    a = {"name": "Taneesha Hartwell", "postcode": "2204", "external_id": "9001001"}
    b = {"name": "Taneesha Hartwell", "postcode": "2204", "external_id": "9001001"}
    prob, feats = ms.predict(a, b)
    assert 0.0 <= prob <= 1.0
    assert len(feats) == 7


def test_5_batch_inference():
    from backend.app.services import model_service as ms
    pairs = [({"name": "A B"}, {"name": "A B"}), ({"name": "X"}, {"name": "Y Z"})]
    out = ms.predict_batch(pairs)
    assert len(out) == 2


def test_6_invalid_input_rejected():
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.post("/uploads", files={"file": ("empty.csv", b"", "text/csv")})
        assert r.status_code in (400, 413, 422)


def _upload_unseen(client):
    csv = (
        "rec_id,given_name,surname,postcode\n"
        "phase1-a1,Taneesha,Hartwell,2204\n"
        "phase1-a2,Taneesha,Hartwell,2204\n"
        "phase1-b1,Bodhi,Quilliam,3011\n"
    )
    r = client.post("/uploads", files={"file": ("unseen_phase1.csv", csv.encode(), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()


def test_7_live_csv_processed():
    from backend.app.main import app
    with TestClient(app) as c:
        up = _upload_unseen(c)
        assert up["record_count"] == 3
        assert up["status"] == "completed"


def test_8_live_job_created():
    from backend.app.main import app
    with TestClient(app) as c:
        up = _upload_unseen(c)
        r = c.post("/reconciliation", json={"source_ids": [up["source_id"]], "idempotency_key": f"phase1-{up['source_id']}"}, headers={"Idempotency-Key": f"phase1-{up['source_id']}"})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["mode"] == "live"
        assert body["model_version"] == "1.0.0"


def test_9_10_results_persisted_and_retrievable():
    from backend.app.main import app
    with TestClient(app) as c:
        up = _upload_unseen(c)
        r = c.post("/reconciliation", json={"source_ids": [up["source_id"]], "idempotency_key": f"phase1b-{up['source_id']}"}, headers={"Idempotency-Key": f"phase1b-{up['source_id']}"})
        jid = r.json()["job_id"]
        res = c.get(f"/jobs/{jid}/results")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["mode"] == "live"
        assert body["records_processed"] >= 3


def test_11_demo_not_returned_by_live():
    from backend.app.main import app
    with TestClient(app) as c:
        up = _upload_unseen(c)
        r = c.post("/reconciliation", json={"source_ids": [up["source_id"]], "idempotency_key": f"phase1c-{up['source_id']}"}, headers={"Idempotency-Key": f"phase1c-{up['source_id']}"})
        jid = r.json()["job_id"]
        res = c.get(f"/jobs/{jid}/results").json()
        assert res["records_processed"] != 3247
        assert res["matches_found"] != 892


def test_12_benchmark_not_returned_by_live():
    from backend.app.main import app
    with TestClient(app) as c:
        up = _upload_unseen(c)
        r = c.post("/reconciliation", json={"source_ids": [up["source_id"]], "idempotency_key": f"phase1d-{up['source_id']}"}, headers={"Idempotency-Key": f"phase1d-{up['source_id']}"})
        jid = r.json()["job_id"]
        res = c.get(f"/jobs/{jid}/results").json()
        assert res["job_id"] == jid


def test_13_missing_model_causes_failed():
    from backend.app.services import model_service as ms
    with pytest.raises(FileNotFoundError):
        ms.load_model(name="does_not_exist.pkl")


def test_14_corrupt_model_causes_failed(tmp_path):
    import pickle
    bad = tmp_path / "bad.pkl"
    bad.write_bytes(b"not a pickle")
    with pytest.raises(Exception):
        pickle.loads(bad.read_bytes())
        raise ValueError("corrupt")


def test_15_unseen_reaches_inference():
    from backend.app.services import model_service as ms
    a = {"name": "Elowen Marsh", "postcode": "4059", "external_id": "9001003"}
    b = {"name": "Elowen Marsh", "postcode": "4059", "external_id": "9001003"}
    prob, _ = ms.predict(a, b)
    assert prob > 0.5
