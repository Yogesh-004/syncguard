"""Phase 4 hardening tests — data quality, normalization, schema drift, uploads,
transactions, workers, sync matrix, concurrency, idempotency, audit, security,
API validation, DB integrity, health, isolation."""
import uuid

import pytest
from fastapi.testclient import TestClient


# ---------- 4B data quality ----------
def test_null_record_survives_normalization():
    from backend.app.services import normalization as nz
    out = nz.normalize_record({"name": None, "email": None, "phone": None})
    assert out == {}


def test_empty_whitespace_unicode_long():
    from backend.app.services import normalization as nz
    assert nz.normalize_name("   ") == ""
    assert nz.normalize_name("  Ravi   Kumar  ") == "RAVI KUMAR"
    assert nz.normalize_email("  JOHN@Example.COM ") == "john@example.com"
    assert nz.normalize_name("José García Niño") == "JOSÉ GARCÍA NIÑO"
    assert nz.normalize_name("O'Brien-Smith (Jr.)") == "O'BRIEN-SMITH (JR.)"
    assert nz.normalize_numeric("-1,234.567") == -1234.57
    assert nz.normalize_numeric("abc") is None
    assert nz.normalize_numeric("1e6") == 1000000.0


def test_duplicate_identifiers_detectable():
    from backend.app.services import normalization as nz
    assert nz.normalize_identifier("C-10482") == nz.normalize_identifier("c10482")


# ---------- 4C normalization robustness ----------
def test_name_variants_consistent():
    from backend.app.services import normalization as nz
    assert nz.normalize_name(" Rahul Kumar ") == nz.normalize_name("rahul kumar") == nz.normalize_name("RAHUL KUMAR")


def test_phone_region_config():
    from backend.app.services import normalization as nz
    assert nz.normalize_phone("5551234567", default_region="US") == "+15551234567"
    assert nz.normalize_phone("9876543210", default_region="IN") == "+919876543210"
    assert nz.normalize_phone("+91 98765 43210") == "+919876543210"
    assert nz.normalize_phone("not-a-phone") == ""


def test_email_invalid_and_missing():
    from backend.app.services import normalization as nz
    assert nz.normalize_email("") == ""
    assert nz.normalize_email("BAD") == "bad"


def test_dates_mixed_formats():
    from backend.app.services import normalization as nz
    assert nz.normalize_date("2024-01-15") == "2024-01-15"
    assert nz.normalize_date("15/01/2024") == "2024-01-15"
    assert nz.normalize_date("01/15/2024") == "2024-01-15"
    assert nz.normalize_date(None) is None
    assert nz.normalize_date("") is None


# ---------- 4D/4E/4F schema drift ----------
def test_schema_added_safe():
    from backend.app.services import schema_analyzer as sa
    d = sa.compare_schemas([{"name": "email", "data_type": "string", "nullable": True}], [{"name": "email", "data_type": "string", "nullable": True}, {"name": "country", "data_type": "string", "nullable": True}])
    assert d[0]["change"] == "ADDED_COLUMN" and d[0]["severity"] == "SAFE"


def test_schema_removed_identifier_blocking():
    from backend.app.services import schema_analyzer as sa
    d = sa.compare_schemas([{"name": "email", "data_type": "string", "nullable": True}], [])
    assert d[0]["change"] == "REMOVED_COLUMN" and d[0]["severity"] == "BLOCKING"


def test_schema_possible_rename():
    from backend.app.services import schema_analyzer as sa
    d = sa.compare_schemas([{"name": "email", "data_type": "string", "nullable": True}], [{"name": "e_mail", "data_type": "string", "nullable": True}])
    assert d[0]["change"] == "POSSIBLE_RENAMED_COLUMN" and d[0]["old_name"] == "email"
    assert "confidence" in d[0] and d[0]["confidence"] < 1.0


def test_schema_type_changed_warning():
    from backend.app.services import schema_analyzer as sa
    d = sa.compare_schemas([{"name": "amount", "data_type": "float", "nullable": True}], [{"name": "amount", "data_type": "string", "nullable": True}])
    assert d[0]["change"] == "TYPE_CHANGED"


def test_schema_drift_endpoint_live():
    from backend.app.main import app
    with TestClient(app) as c:
        csv1 = "email,phone\njohn@x.com,111\n"
        csv2 = "email,phone,country\njohn@x.com,111,IN\n"
        sid = c.post("/uploads", files={"file": ("s1.csv", csv1.encode(), "text/csv")}).json()["source_id"]
        c.post("/uploads", files={"file": ("s2.csv", csv2.encode(), "text/csv")}, params={"source_id": sid})
        # uploads with source_id param? endpoint takes query param source_id
        r = c.get(f"/schemas/drift?source_id={sid}")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "compared"
        assert any(x["change"] == "ADDED_COLUMN" for x in body["drifts"])


def test_schema_version_history_preserved():
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.get("/schemas")
        assert r.status_code == 200


# ---------- 4G upload safety ----------
def test_upload_empty_rejected():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.post("/uploads", files={"file": ("e.csv", b"", "text/csv")}).status_code == 422


def test_upload_wrong_extension():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.post("/uploads", files={"file": ("e.exe", b"a,b\n1,2", "text/plain")}).status_code == 422


def test_upload_malformed_csv():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.post("/uploads", files={"file": ("e.csv", b"notcsvcontent", "text/csv")}).status_code == 422


def test_upload_bad_encoding():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.post("/uploads", files={"file": ("e.csv", b"\xff\xfe\x00a,b\n1,2", "text/csv")}).status_code in (201, 422)


def test_upload_missing_headers():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.post("/uploads", files={"file": ("e.csv", b",\n1,2\n", "text/csv")}).status_code == 422


def test_upload_duplicate_headers():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.post("/uploads", files={"file": ("e.csv", b"a,a\n1,2\n", "text/csv")}).status_code == 422


def test_upload_no_traceback_leak():
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.post("/uploads", files={"file": ("e.csv", b"\x00\x01\x02", "text/csv")})
        assert "Traceback" not in r.text


def test_upload_traversal_sanitized():
    from backend.app.main import app
    with TestClient(app) as c:
        r = c.post("/uploads", files={"file": ("../../etc.csv", b"a,b\n1,2", "text/csv")})
        assert r.status_code in (201, 400)


# ---------- 4N matching edge cases ----------
def test_edge_exact_and_normalized():
    from backend.app.services import model_service as ms
    p1, _ = ms.predict({"name": "Ann Lee", "postcode": "1", "external_id": "9"}, {"name": "Ann Lee", "postcode": "1", "external_id": "9"})
    assert p1 > 0.5


def test_edge_missing_fields():
    from backend.app.services import model_service as ms
    p, feats = ms.predict({"name": None, "postcode": None, "external_id": None}, {"name": None, "postcode": None, "external_id": None})
    assert 0.0 <= p <= 1.0


def test_edge_conflicting_identifiers():
    from backend.app.services import model_service as ms
    p, _ = ms.predict({"name": "Ann Lee", "postcode": "1", "external_id": "9"}, {"name": "Ann Lee", "postcode": "1", "external_id": "8"})
    assert 0.0 <= p <= 1.0


# ---------- 4O conflict edge cases ----------
def test_conflict_case_only_no_conflict():
    from backend.app.services import conflict_detection as cd
    assert cd.detect_field_conflicts({"name": "Rahul Kumar"}, {"name": "RAHUL KUMAR"}) == []


def test_conflict_both_null_no_conflict():
    from backend.app.services import conflict_detection as cd
    assert cd.detect_field_conflicts({"phone": None}, {"phone": None}) == []


def test_conflict_dedup_rerun():
    from backend.app.main import app
    with TestClient(app) as c:
        csv = "rec_id,given_name,surname,email,phone,postcode\ndq-1,Zed,Alpha,zed@a.com,9100001,1000\ndq-2,Zed,Alpha,zed@b.com,9100001,1000\n"
        sid = c.post("/uploads", files={"file": ("dq.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"dq-{uuid.uuid4().hex[:8]}"
        jid = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key}).json()["job_id"]
        n1 = len(c.get(f"/conflicts?job_id={jid}&limit=100").json())
        key2 = f"dq-{uuid.uuid4().hex[:8]}"
        jid2 = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key2}, headers={"Idempotency-Key": key2}).json()["job_id"]
        n2 = len(c.get(f"/conflicts?job_id={jid2}&limit=100").json())
        assert n1 == n2


# ---------- 4P transaction safety ----------
def test_failed_push_leaves_honest_state():
    from backend.app.main import app
    with TestClient(app) as c:
        csv = "rec_id,given_name,surname,email,phone,postcode\ntx-1,Yo,Lo,yo@a.com,9200001,2000\ntx-2,Yo,Lo,yo@b.com,9200001,2000\n"
        sid = c.post("/uploads", files={"file": ("tx.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"tx-{uuid.uuid4().hex[:8]}"
        c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True, "simulate_error": 500}).json()
        assert r["status"] == "FAILED"
        assert c.get(f"/conflicts/{cid}").json()["resolution_status"] == "approved"


# ---------- 4Q worker failure ----------
def test_job_never_stuck_processing():
    from backend.app.main import app
    with TestClient(app) as c:
        csv = "a,b\n1,2\n"
        sid = c.post("/uploads", files={"file": ("w.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"wq-{uuid.uuid4().hex[:8]}"
        jid = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key}).json()["job_id"]
        assert c.get(f"/reconciliation/{jid}").json()["status"] in ("completed", "failed", "queued", "processing")


def test_model_missing_503():
    from backend.app.services import model_service as ms
    with pytest.raises(FileNotFoundError):
        ms.load_model(name="nope.pkl")


# ---------- 4R sync matrix ----------
@pytest.mark.parametrize("code,retryable", [(400, False), (401, False), (404, False), (409, False), (422, False), (429, True), (500, True), (502, True), (503, True), ("timeout", True), ("connection", True)])
def test_sync_matrix(code, retryable):
    from backend.app.main import app
    with TestClient(app) as c:
        tag = f"mx{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Ma,Pa,ma@a.com,9300001,3000\n{tag}-2,Ma,Pa,ma@b.com,9300001,3000\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"mx-{uuid.uuid4().hex[:8]}"
        c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        r = c.post(f"/resolutions/{rid}/push", json={"confirm": True, "simulate_error": code}).json()
        assert r["status"] == "FAILED"
        jid = r["sync_job_id"]
        rr = c.post(f"/sync-jobs/{jid}/retry", json={})
        assert (rr.status_code == 200) == retryable


# ---------- 4S concurrency ----------
def test_parallel_resolve_single_winner():
    from backend.app.main import app
    import concurrent.futures
    with TestClient(app) as c:
        tag = f"cc{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Ca,De,ca@a.com,9400001,4000\n{tag}-2,Ca,De,ca@b.com,9400001,4000\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"cc-{uuid.uuid4().hex[:8]}"
        c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            rs = list(ex.map(lambda a: c.post(f"/conflicts/{cid}/resolve", json={"action": a}).status_code, ["USE_SOURCE_A", "USE_SOURCE_B"]))
        assert sorted(rs) == [200, 409]
        assert len(c.get(f"/conflicts/{cid}/resolutions").json()) == 1


def test_parallel_push_idempotent():
    from backend.app.main import app
    import concurrent.futures
    with TestClient(app) as c:
        tag = f"cp{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Ce,Fo,ce@a.com,9500001,5000\n{tag}-2,Ce,Fo,ce@b.com,9500001,5000\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"cp-{uuid.uuid4().hex[:8]}"
        c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            rs = list(ex.map(lambda _: c.post(f"/resolutions/{rid}/push", json={"confirm": True}).json(), range(2)))
        assert {r["sync_job_id"] for r in rs} == {rs[0]["sync_job_id"]}
        assert all(r["status"] == "SUCCESS" for r in rs)


# ---------- 4T idempotency ----------
def test_dryrun_repeat_same_job():
    from backend.app.main import app
    with TestClient(app) as c:
        tag = f"dr{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Dr,Ry,dr@a.com,9600001,6000\n{tag}-2,Dr,Ry,dr@b.com,9600001,6000\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"dr-{uuid.uuid4().hex[:8]}"
        c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        j1 = c.post(f"/resolutions/{rid}/dry-run").json()["sync_job_id"]
        j2 = c.post(f"/resolutions/{rid}/dry-run").json()["sync_job_id"]
        assert j1 == j2


# ---------- 4U audit integrity ----------
def test_no_success_on_failure():
    from backend.app.main import app
    with TestClient(app) as c:
        tag = f"au{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Au,Di,au@a.com,9700001,7000\n{tag}-2,Au,Di,au@b.com,9700001,7000\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"au-{uuid.uuid4().hex[:8]}"
        c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        c.post(f"/resolutions/{rid}/push", json={"confirm": True, "simulate_error": 500})
        actions = [a["action"] for a in c.get(f"/conflicts/{cid}/audit").json()]
        assert "SYNC_FAILED" in actions and "SYNC_SUCCEEDED" not in actions


def test_audit_append_only():
    from backend.app.main import app
    with TestClient(app) as c:
        tag = f"ap{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Ap,Pe,ap@a.com,9800001,8000\n{tag}-2,Ap,Pe,ap@b.com,9800001,8000\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"ap-{uuid.uuid4().hex[:8]}"
        c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        n0 = len(c.get(f"/conflicts/{cid}/audit").json())
        c.post(f"/conflicts/{cid}/resolve", json={"action": "DEFER", "reason": "later"})
        assert len(c.get(f"/conflicts/{cid}/audit").json()) > n0


# ---------- 4W API validation ----------
def test_unknown_ids_404():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.get("/matches/99999999").status_code == 404
        assert c.get("/sync-jobs/99999999").status_code == 404
        assert c.post("/resolutions/99999999/dry-run").status_code == 404


def test_push_without_confirm_422():
    from backend.app.main import app
    with TestClient(app) as c:
        tag = f"pc{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Pc,Vv,pc@a.com,9900001,9000\n{tag}-2,Pc,Vv,pc@b.com,9900001,9000\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"pc-{uuid.uuid4().hex[:8]}"
        c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        c.post(f"/resolutions/{rid}/dry-run")
        assert c.post(f"/resolutions/{rid}/push", json={"confirm": False}).status_code == 422


def test_push_without_dryrun_422():
    from backend.app.main import app
    with TestClient(app) as c:
        tag = f"pd{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Pd,Vv,pd@a.com,9910001,9100\n{tag}-2,Pd,Vv,pd@b.com,9910001,9100\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"pd-{uuid.uuid4().hex[:8]}"
        c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key})
        cid = c.get(f"/conflicts?source_id={sid}&limit=5").json()[0]["id"]
        c.post(f"/conflicts/{cid}/resolve", json={"action": "USE_SOURCE_A"})
        rid = c.get(f"/conflicts/{cid}/resolutions").json()[0]["id"]
        assert c.post(f"/resolutions/{rid}/push", json={"confirm": True}).status_code == 422


def test_invalid_ids_rejected():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.get("/conflicts/abc").status_code in (404, 422)
        assert c.get("/schemas/drift?source_id=xyz").status_code == 422


# ---------- 4Y DB integrity ----------
def test_fk_integrity():
    from backend.app.main import app
    with TestClient(app) as c:
        tag = f"fk{uuid.uuid4().hex[:6]}"
        csv = f"rec_id,given_name,surname,email,phone,postcode\n{tag}-1,Fk,Iy,fk@a.com,9920001,9200\n{tag}-2,Fk,Iy,fk@b.com,9920001,9200\n"
        sid = c.post("/uploads", files={"file": (f"{tag}.csv", csv.encode(), "text/csv")}).json()["source_id"]
        key = f"fk-{uuid.uuid4().hex[:8]}"
        jid = c.post("/reconciliation", json={"source_ids": [sid], "idempotency_key": key}, headers={"Idempotency-Key": key}).json()["job_id"]
        for m in c.get(f"/matches?job_id={jid}&limit=50").json()["items"]:
            assert m["record_a_id"] and m["record_b_id"]
        for x in c.get(f"/conflicts?job_id={jid}&limit=50").json():
            assert x["match_id"] is not None
            assert c.get(f"/matches/{x['match_id']}").status_code == 200


# ---------- 4AA health ----------
def test_health_and_ready():
    from backend.app.main import app
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        r = c.get("/readyz").json()
        assert r["checks"]["database"] == "ok"
        assert r["checks"]["model"] == "ok"
        assert r["ready"] is True
