"""FastAPI route definitions — spec-compliant + backward compatible."""
import hashlib
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from sqlalchemy import or_
from backend.app.db.database import get_db
from backend.app.db.models import SourceModel, RecordModel, MatchModel, ConflictModel, ReconciliationJobModel, AuditLogModel, SchemaModel, SyncJobModel, PresenceObservationModel
from backend.app.schemas.records import RecordCreate, Record, SourceCreate, Source, UploadResponse
from backend.app.schemas.matching import MatchResult
from backend.app.schemas.conflicts import Conflict, ResolutionRequest, ResolutionResponse
from backend.app.schemas.jobs import JobCreate, Job, JobStatusResponse
from backend.app.schemas.sources import Schema, SchemaDriftReport
from backend.app.schemas.base import StatusEnum, PaginatedResponse
from backend.app.services.matching import MatchingEngine
from backend.app.services.reconciliation import ReconciliationEngine
from backend.app.services.schema_analyzer import SchemaAnalyzer
from backend.app.services.audit import AuditService
from backend.app.services import presence as presence_svc
from backend.app.connectors.csv_connector import CSVConnector
from backend.app.connectors.json_connector import JSONConnector
from backend.app.connectors.rest_connector import RESTConnector
from backend.app.core.config import settings
from backend.app.core.logging import logger

router = APIRouter()
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name)
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    if not name or name.startswith("."):
        name = f"upload_{uuid.uuid4().hex[:8]}.csv"
    return name[:120]


def _idempotency_key(body_key: Optional[str], header_key: Optional[str], payload: str) -> str:
    if body_key:
        return body_key
    if header_key:
        return header_key
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


# ---------- Sources ----------

@router.get("/sources", response_model=List[Source])
def list_sources(db: Session = Depends(get_db)):
    return db.query(SourceModel).filter(SourceModel.is_active == True).all()


@router.post("/sources", response_model=Source, status_code=status.HTTP_201_CREATED)
def create_source(source: SourceCreate, db: Session = Depends(get_db)):
    model = SourceModel(name=source.name, source_type=source.source_type, connection_string=source.connection_string, config=source.config)
    db.add(model)
    db.commit()
    db.refresh(model)
    logger.info("Source created", name=source.name)
    return model


@router.get("/sources/{source_id}", response_model=Source)
def get_source(source_id: int, db: Session = Depends(get_db)):
    m = db.query(SourceModel).filter(SourceModel.id == source_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Source not found")
    return m


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    m = db.query(SourceModel).filter(SourceModel.id == source_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Source not found")
    m.is_active = False
    db.commit()
    return None


# ---------- Uploads ----------

@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    source_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    import csv, io, json as js
    filename = _sanitize_filename(file.filename or "upload.csv")
    if ".." in (file.filename or "") or "/" in (file.filename or "") or "\\" in (file.filename or ""):
        raise HTTPException(status_code=400, detail="Invalid filename")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("csv", "json"):
        raise HTTPException(status_code=422, detail="Only csv and json allowed")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large max {settings.MAX_UPLOAD_SIZE_MB}MB")
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="Empty file")
    if ext == "csv" and b"," not in content[:1024] and b"\n" not in content[:1024]:
        raise HTTPException(status_code=422, detail="Malformed csv")
    if ext == "json":
        try:
            js.loads(content)
        except Exception:
            raise HTTPException(status_code=422, detail="Malformed json")
    # Create or get source for live upload — isolated from training data
    src = None
    if source_id and str(source_id).isdigit():
        src = db.query(SourceModel).filter(SourceModel.id == int(source_id)).first()
    if not src:
        src = SourceModel(name=f"Live: {filename}", source_type="csv" if ext=="csv" else "json", config={"live": True, "filename": filename, "training": False})
        db.add(src)
        db.commit()
        db.refresh(src)
    # Parse and store records — live dataset alone (utf-8-sig strips BOM)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="Invalid encoding: file must be UTF-8")
    records_data = []
    if ext == "csv":
        try:
            reader = csv.DictReader(io.StringIO(text))
        except Exception:
            raise HTTPException(status_code=422, detail="Malformed csv: header unreadable")
        if not reader.fieldnames:
            raise HTTPException(status_code=422, detail="Missing headers: csv has no header row")
        headers = [h for h in reader.fieldnames if h and h.strip()]
        if len(headers) != len(reader.fieldnames):
            raise HTTPException(status_code=422, detail="Missing headers: csv has empty column names")
        if len(set(headers)) != len(headers):
            raise HTTPException(status_code=422, detail="Duplicate headers in csv")
        for row in reader:
            if row is None:
                continue
            clean = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k and k.strip()}
            if not clean:
                continue
            for k, v in clean.items():
                if isinstance(v, str) and len(v) > settings.MAX_FIELD_CHARS:
                    raise HTTPException(status_code=422, detail=f"Huge field value in column '{k}' (>{settings.MAX_FIELD_CHARS} chars)")
            records_data.append(clean)
            if len(records_data) > settings.MAX_UPLOAD_ROWS:
                raise HTTPException(status_code=413, detail=f"Too many rows: max {settings.MAX_UPLOAD_ROWS}")
        if not records_data:
            raise HTTPException(status_code=422, detail="Empty file: csv has headers but no data rows")
    else:
        data = js.loads(text)
        if isinstance(data, list):
            records_data = [r for r in data if isinstance(r, dict)]
        elif isinstance(data, dict):
            records_data = [data]
        else:
            raise HTTPException(status_code=422, detail="Malformed json: expected object or array of objects")
        if not records_data:
            raise HTTPException(status_code=422, detail="Empty file: json has no records")
        if len(records_data) > settings.MAX_UPLOAD_ROWS:
            raise HTTPException(status_code=413, detail=f"Too many rows: max {settings.MAX_UPLOAD_ROWS}")
    # Store
    count = 0
    for idx, rec in enumerate(records_data):
        rid = rec.get("rec_id") or rec.get("id") or rec.get("customer_id") or f"live-{idx}"
        nd = {}
        try:
            nd = normalize_record(rec)
        except:
            nd = rec
        rm = RecordModel(source_id=src.id, source_record_id=str(rid), data=rec, raw_data=rec, normalized_data=nd)
        db.add(rm)
        count += 1
    db.commit()
    # Schema versioning: compare against latest stored schema for re-used sources
    from backend.app.services import schema_analyzer as _sa
    new_schema = _sa.infer_schema(records_data)
    prev = db.query(SchemaModel).filter(SchemaModel.source_id == src.id).order_by(SchemaModel.version.desc()).first()
    drift_note = ""
    if prev and prev.fields:
        drifts = _sa.compare_schemas(prev.fields, new_schema)
        blocking = [d for d in drifts if d.get("severity") == "BLOCKING"]
        if drifts:
            db.add(AuditLogModel(action="SCHEMA_DRIFT", entity_type="source", entity_id=str(src.id),
                                 details={"from_version": prev.version, "drifts": drifts}))
            worst = "BLOCKING" if blocking else ("WARNING" if any(d.get("severity") == "WARNING" for d in drifts) else "SAFE")
            drift_note = f" Schema drift vs v{prev.version}: {len(drifts)} change(s), worst={worst}."
            logger.info("SCHEMA_DRIFT", source_id=src.id, changes=len(drifts), worst=worst)
    version = (prev.version + 1) if prev else 1
    db.add(SchemaModel(source_id=src.id, fields=new_schema, field_count=len(new_schema), version=version))
    db.commit()
    upload_id = str(uuid.uuid4())
    logger.info("Live upload stored", filename=filename, source_id=src.id, count=count, schema_version=version)
    return UploadResponse(upload_id=upload_id, source_id=str(src.id), filename=filename, record_count=count, status="completed", message=f"Live dataset stored: {count} records (schema v{version}).{drift_note} All features now isolated to this dataset until deleted")


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str):
    raise HTTPException(status_code=404, detail="Upload receipts are not retained; use source_id from the upload response with GET /records?source_id=")


# ---------- Records (legacy) ----------

@router.get("/records")
def list_records(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), limit: Optional[int] = Query(None, ge=1, le=500), source_id: Optional[str] = None, is_processed: Optional[bool] = None, db: Session = Depends(get_db)):
    if limit is not None:
        page_size = limit
    q = db.query(RecordModel)
    if source_id:
        try:
            q = q.filter(RecordModel.source_id == int(source_id))
        except ValueError:
            pass
    if is_processed is not None:
        q = q.filter(RecordModel.is_processed == is_processed)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [{"id": r.id, "source_id": r.source_id, "source_record_id": r.source_record_id, "data": r.data, "raw_data": r.raw_data, "normalized_data": r.normalized_data, "is_processed": r.is_processed, "created_at": r.created_at.isoformat() if r.created_at else None} for r in items]}


@router.post("/records/upload", response_model=UploadResponse)
def upload_records_legacy(source_id: str, filename: str, db: Session = Depends(get_db)):
    upload_id = str(uuid.uuid4())
    return UploadResponse(upload_id=upload_id, source_id=source_id, filename=_sanitize_filename(filename), record_count=0, status="pending", message="Upload accepted")


# ---------- Reconciliation (spec) ----------

def _run_reconciliation_inline(job_id: int, source_ids: list, model_version: str):
    """Execute the existing inline ML pipeline for one job in the background.

    Same pipeline body as the former in-request execution, with its own DB
    session (the request session is closed once the 202 responds). The
    queued->processing claim guarantees a job runs at most once even if
    scheduled twice. All failures persist failed status + error_message.
    """
    from backend.app.db.database import SessionLocal
    from backend.app.services import model_service as _model_service
    db = SessionLocal()
    try:
        model = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.id == job_id).first()
        if not model:
            logger.error("BACKGROUND_JOB_MISSING", job_id=job_id)
            return
        claimed = db.query(ReconciliationJobModel).filter(
            ReconciliationJobModel.id == job_id,
            ReconciliationJobModel.status == "queued",
        ).update({"status": "processing",
                  "started_at": __import__("datetime").datetime.utcnow()},
                 synchronize_session=False) == 1
        if not claimed:
            db.rollback()
            logger.info("BACKGROUND_JOB_ALREADY_RUNNING", job_id=job_id)
            return
        db.commit()
        db.refresh(model)
        try:
            # load records for sources (or all if empty)
            q = db.query(RecordModel)
            if source_ids:
                try:
                    sids = [int(s) for s in source_ids if str(s).isdigit()]
                    if sids:
                        q = q.filter(RecordModel.source_id.in_(sids))
                except: pass
            total_available = q.count()
            if total_available > settings.MAX_JOB_RECORDS:
                raise RuntimeError(f"Job input {total_available} records exceeds MAX_JOB_RECORDS={settings.MAX_JOB_RECORDS} (O(n²) guard) — split the dataset or raise the limit deliberately")
            records = q.limit(settings.MAX_JOB_RECORDS).all()
            model.total_records = len(records)
            db.commit()
            # run ML matching (Phase 2: MATCH/POSSIBLE_MATCH tiers, field-level conflicts)
            from backend.app.services import conflict_detection as _cd
            dicts=[]
            for r in records:
                d = dict(r.normalized_data or r.data or {})
                d["id"]=r.id
                if "name" not in d and "given_name" in d:
                    d["name"]=f"{d.get('given_name','')} {d.get('surname','')}".strip()
                dicts.append(d)
            t0 = __import__("time").time()
            engine = MatchingEngine(use_ml=True, strict_ml=True)
            th_match = settings.MATCH_THRESHOLD
            th_poss = settings.POSSIBLE_MATCH_THRESHOLD
            # Multi-pass candidate generation (Phase 4.6): exhaustive for small inputs
            # (no blocking loss), union blocking above EXHAUSTIVE_PAIR_LIMIT.
            from backend.app.services import blocking as _bl
            n_pairs = len(dicts) * (len(dicts) - 1) // 2
            passes = [p.strip() for p in settings.BLOCKING_PASSES.split(",") if p.strip()]
            if n_pairs <= settings.EXHAUSTIVE_PAIR_LIMIT:
                candidates, provenance = None, {}
                logger.info("CANDIDATES_EXHAUSTIVE", job_id=model.id, pairs=n_pairs)
            else:
                gen = _bl.generate_candidates(dicts, passes=passes, max_block_size=settings.MAX_BLOCK_SIZE, max_candidates=settings.MAX_CANDIDATES)
                candidates, provenance = gen["candidates"], gen["provenance"]
                logger.info("CANDIDATES_BLOCKED", job_id=model.id, passes=passes, candidates=len(candidates), stats=gen["stats"])
            evaluated = engine.evaluate_pairs(dicts, nomatch_sample=settings.PERSIST_NOMATCH_SAMPLE, candidates=candidates, provenance=provenance)
            matches = evaluated["kept"]
            nomatch = evaluated["nomatch_sample"]
            # persist matches with dedupe (same pair + job → skip); verdict columns filled
            persisted = []
            for m in matches[:100]:
                decision = (m.evidence or {}).get("decision") or _model_service.decide(m.confidence, th_match, th_poss)
                ev = dict(m.evidence or {})
                ev["decision"] = decision
                ev["model_version"] = model_version
                ev["job_id"] = model.id
                a, b = (m.record_a_id, m.record_b_id) if m.record_a_id < m.record_b_id else (m.record_b_id, m.record_a_id)
                dup = db.query(MatchModel).filter(MatchModel.record_a_id == a, MatchModel.record_b_id == b, MatchModel.entity_group_id == f"job-{model.id}").first()
                if dup:
                    persisted.append(dup)
                    continue
                mm = MatchModel(record_a_id=a, record_b_id=b, confidence=m.confidence, match_method="ml", matched_fields=m.matched_fields, evidence=ev, entity_group_id=f"job-{model.id}",
                                final_confidence=m.confidence, risk=ev.get("risk"), auto_resolvable=bool(ev.get("auto_resolvable")), recommendation=ev.get("recommendation"))
                db.add(mm)
                persisted.append(mm)
                db.add(AuditLogModel(action="MATCH_CREATED", entity_type="match", entity_id=None,
                                     job_id=model.id,
                                     details={"job_id": model.id, "record_a_id": a, "record_b_id": b, "decision": decision, "confidence": m.confidence}))
            # persist nearest-miss NO_MATCH sample (labeled, bounded — not hidden, not exhaustive)
            for m in nomatch:
                ev = dict(m.evidence or {})
                ev["decision"] = "NO_MATCH"
                ev["model_version"] = model_version
                ev["job_id"] = model.id
                a, b = (m.record_a_id, m.record_b_id) if m.record_a_id < m.record_b_id else (m.record_b_id, m.record_a_id)
                dup = db.query(MatchModel).filter(MatchModel.record_a_id == a, MatchModel.record_b_id == b, MatchModel.entity_group_id == f"job-{model.id}").first()
                if dup:
                    continue
                db.add(MatchModel(record_a_id=a, record_b_id=b, confidence=m.confidence, match_method="ml", matched_fields=m.matched_fields, evidence=ev, entity_group_id=f"job-{model.id}",
                                  final_confidence=m.confidence, risk=ev.get("risk"), auto_resolvable=False, recommendation=ev.get("recommendation")))
                db.add(AuditLogModel(action="MATCH_CREATED", entity_type="match", entity_id=None,
                                     job_id=model.id,
                                     details={"job_id": model.id, "record_a_id": a, "record_b_id": b, "decision": "NO_MATCH", "confidence": m.confidence, "sampled": True}))
            db.flush()
            for mm in persisted:
                if mm.id and (mm.evidence or {}).get("decision"):
                    db.add(AuditLogModel(action="MATCH_CLASSIFIED", entity_type="match", entity_id=str(mm.id),
                                         job_id=model.id,
                                         details={"job_id": model.id, "decision": (mm.evidence or {}).get("decision"), "confidence": mm.confidence, "risk": mm.risk, "auto_resolvable": mm.auto_resolvable}))
            # field-level conflicts for MATCH and POSSIBLE_MATCH tiers (NO_MATCH excluded);
            # POSSIBLE pairs carry disagreements that need human review — hiding them would lose reviewability
            n_conf = 0
            for m, mm in zip(matches[:100], persisted):
                decision = (m.evidence or {}).get("decision", "")
                if decision not in ("MATCH", "POSSIBLE_MATCH"):
                    continue
                ra = next((x for x in records if x.id==m.record_a_id), None)
                rb = next((x for x in records if x.id==m.record_b_id), None)
                if not ra or not rb:
                    continue
                fields = _cd.detect_field_conflicts(ra.data or {}, rb.data or {})
                for f in fields:
                    dupc = db.query(ConflictModel).filter(ConflictModel.record_a_id==mm.record_a_id, ConflictModel.record_b_id==mm.record_b_id, ConflictModel.match_id==mm.id).all()
                    if any((d.get("conflicting_fields") or [{}])[0].get("field_name")==f["field_name"] for d in dupc):
                        continue
                    rec, reason = _cd.recommend(f["source_value"], f["target_value"])
                    risk, why = _cd.classify_risk(f["field_name"], f["outcome"], m.confidence, len(fields))
                    auto = bool((m.evidence or {}).get("auto_resolvable")) and risk == "low"
                    cm = ConflictModel(record_a_id=mm.record_a_id, record_b_id=mm.record_b_id, match_id=mm.id, confidence=m.confidence, conflicting_fields=[{"field_name": f["field_name"], "conflict_type": f["conflict_type"], "values": f["values"], "sources": f["sources"]}], evidence={**m.evidence, "conflict_reason": reason, "risk_reason": why, "job_id": model.id, "model_version": model_version}, risk_level=risk, recommendation=(m.evidence or {}).get("recommendation") if auto else ("REVIEW REQUIRED" if risk in ("HIGH", "CRITICAL", "MEDIUM") else rec), resolution_status="pending", auto_resolvable=auto)
                    db.add(cm)
                    n_conf += 1
            db.flush()
            for cm in db.query(ConflictModel).filter(ConflictModel.match_id.in_([mm.id for mm in persisted if mm.id])).all():
                db.add(AuditLogModel(action="CONFLICT_CREATED", entity_type="conflict", entity_id=str(cm.id),
                                     job_id=model.id,
                                     details={"job_id": model.id, "match_id": cm.match_id, "field": (cm.conflicting_fields or [{}])[0].get("field_name"), "risk": cm.risk_level}))
            # presence side output (Phase 5C-W): read-only derivation over the
            # comparison's record sets. Orthogonal to matching: no feedback into
            # matcher/blocking/decision/conflicts. Failure-isolated: a presence
            # error is logged and cleaned, never fails the comparison.
            try:
                from backend.app.services import presence as _ps
                _by_source: Dict[str, List] = {}
                for _r in records:
                    _by_source.setdefault(str(_r.source_id), []).append(_r)
                _sides = sorted(_by_source)
                if len(_sides) >= 2:
                    _sa, _sb = _sides[0], _sides[1]
                    _scope = {"source_a": _sa, "source_b": _sb,
                              "snapshot_a": f"source:{_sa}", "snapshot_b": f"source:{_sb}"}
                    _keys_a = [str(_r.source_record_id or _r.id) for _r in _by_source[_sa]]
                    _keys_b = [str(_r.source_record_id or _r.id) for _r in _by_source[_sb]]
                    _refs: Dict[str, List[str]] = {}
                    for _r in _by_source[_sa] + _by_source[_sb]:
                        _refs.setdefault(str(_r.source_record_id or _r.id), []).append(str(_r.id))
                    # idempotency: scoped delete-then-insert per comparison (never duplicates)
                    db.query(PresenceObservationModel).filter(PresenceObservationModel.job_id == model.id).delete()
                    _obs = _ps.derive_and_persist(
                        db, _scope, _keys_a, _keys_b,
                        completeness_a="COMPLETE", completeness_b="COMPLETE",
                        job_id=model.id, snapshot_a_ref=f"source:{_sa}",
                        snapshot_b_ref=f"source:{_sb}", key_to_refs=_refs,
                        pipeline_version="5c-w")
                    logger.info("PRESENCE_SIDE_OUTPUT", job_id=model.id, observations=len(_obs))
                else:
                    logger.info("PRESENCE_SKIPPED", job_id=model.id, reason="single-source job is not an A/B comparison")
            except Exception as _pex:
                try:
                    db.query(PresenceObservationModel).filter(PresenceObservationModel.job_id == model.id).delete()
                except Exception:
                    pass
                logger.error("PRESENCE_SIDE_OUTPUT_FAILED", job_id=model.id, error=str(_pex))
            elapsed = round(__import__("time").time() - t0, 3)
            logger.info("MATCHING_COMPLETED", job_id=model.id, candidate_pairs="blocked", matches=len(persisted), conflicts=n_conf, elapsed_s=elapsed)
            model.processed_records = len(records)
            model.progress = 100
            model.status = "completed"
            model.completed_at = __import__("datetime").datetime.utcnow()
            db.commit()
            ran_inline = True
            logger.info("LIVE_DATA_VALIDATED", job_id=model.id, records=len(records))
            logger.info("FEATURE_GENERATION_STARTED", job_id=model.id, pairs=evaluated["evaluated_pairs"])
            logger.info("INFERENCE_STARTED", job_id=model.id, model_version=model_version)
            logger.info("INFERENCE_COMPLETED", job_id=model.id, matches=len(matches), nomatch_sample=len(nomatch))
            logger.info("RESULTS_PERSISTED", job_id=model.id, matches=len(persisted))
            logger.info("LIVE_ANALYSIS_COMPLETED", job_id=model.id, records=len(records), matches=len(matches))
        except Exception as ex:
            logger.error("LIVE_ANALYSIS_FAILED", job_id=model.id, error=str(ex))
            model.status = "failed"
            model.error_message = str(ex)
            db.commit()
    finally:
        db.close()

@router.post("/reconciliation", status_code=status.HTTP_202_ACCEPTED)
def create_reconciliation(
    payload: Dict[str, Any],
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    source_ids = payload.get("source_ids") or payload.get("source_id") or []
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    body_key = payload.get("idempotency_key")
    key = _idempotency_key(body_key, idempotency_key, str(payload))
    from backend.app.services import model_service as _model_service
    try:
        _model_service.load_model()
        model_version = _model_service.get_model_version()
    except Exception as e:
        logger.error("LIVE_ANALYSIS_FAILED", error=f"Model unavailable: {e}")
        raise HTTPException(status_code=503, detail="Model unavailable")
    existing = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.idempotency_key == key).first()
    if existing:
        return {"id": existing.id, "job_id": existing.id, "mode": "live", "model_version": model_version, "status": existing.status, "idempotency_key": key}
    model = ReconciliationJobModel(job_type="reconciliation", source_id=str(source_ids), status="queued", idempotency_key=key, max_retries=3)
    logger.info("LIVE_ANALYSIS_STARTED", job_id="pending", model_version=model_version, sources=str(source_ids))
    db.add(model)
    try:
        db.commit()
        db.refresh(model)
    except IntegrityError:
        db.rollback()
        existing = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.idempotency_key == key).first()
        return {"id": existing.id, "job_id": existing.id, "status": existing.status, "idempotency_key": key}
    # Try Celery, else schedule the existing inline pipeline as a background
    # task so POST returns 202 immediately (long workloads must not block it).
    ran_inline = False
    try:
        from backend.app.workers.tasks import reconcile_task
        # run inline if Redis not available (dev)
        import os
        if os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL"):
            reconcile_task.delay(model.id, str(source_ids), [])
        else:
            raise Exception("no broker, inline")
    except Exception as e:
        logger.info("Running inline ML pipeline (benchmark-connected)", error=str(e))
    if background_tasks is None:
        _run_reconciliation_inline(model.id, list(source_ids), model_version)
    else:
        background_tasks.add_task(_run_reconciliation_inline, model.id, list(source_ids), model_version)
    logger.info("Reconciliation job created", job_id=model.id, inline=ran_inline)
    return {"id": model.id, "job_id": model.id, "mode": "live", "model_version": model_version, "status": model.status, "progress": model.progress, "idempotency_key": key, "total_records": model.total_records}


@router.get("/reconciliation/{job_id}")
def get_reconciliation(job_id: int, db: Session = Depends(get_db)):
    from backend.app.services import model_service as _ms2
    m = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.id == job_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"id": m.id, "job_id": m.id, "mode": "live", "model_version": _ms2.get_model_version(), "status": m.status, "progress": m.progress, "total_records": m.total_records, "processed_records": m.processed_records, "error_message": m.error_message, "created_at": m.created_at}


@router.get("/jobs/{job_id}/results")
def get_job_results(job_id: int, db: Session = Depends(get_db)):
    from backend.app.services import model_service as _ms3
    m = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.id == job_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Job not found")
    matches = db.query(MatchModel).filter(MatchModel.entity_group_id == f"job-{job_id}").all()
    match_ids = [x.id for x in matches]
    conflicts = db.query(ConflictModel).filter(ConflictModel.match_id.in_(match_ids)).all() if match_ids else []
    n_match = sum(1 for x in matches if (x.evidence or {}).get("decision") == "MATCH")
    n_poss = sum(1 for x in matches if (x.evidence or {}).get("decision") == "POSSIBLE_MATCH")
    n_no = sum(1 for x in matches if (x.evidence or {}).get("decision") == "NO_MATCH")
    n = m.processed_records or m.total_records or 0
    return {
        "job_id": job_id, "mode": "live", "model_version": _ms3.get_model_version(),
        "thresholds": {"MATCH": settings.MATCH_THRESHOLD, "POSSIBLE_MATCH": settings.POSSIBLE_MATCH_THRESHOLD},
        "status": m.status, "records_processed": n,
        "matches_found": n_match, "possible_matches": n_poss, "nomatch_sampled": n_no,
        "evaluated_pairs": n * (n - 1) // 2 if n else 0,
        "unmatched": max(0, n - 2 * n_match),
        "matches": [{"id": x.id, "record_a_id": x.record_a_id, "record_b_id": x.record_b_id, "confidence": x.confidence, "decision": (x.evidence or {}).get("decision"), "evidence": x.evidence} for x in matches[:100]],
        "conflicts": len(conflicts),
    }


@router.get("/matches")
def list_matches(job_id: Optional[int] = Query(None), source_id: Optional[str] = Query(None), decision: Optional[str] = Query(None), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    from backend.app.services import model_service as _msm
    q = db.query(MatchModel)
    if job_id:
        q = q.filter(MatchModel.entity_group_id == f"job-{job_id}")
    if source_id and str(source_id).isdigit():
        ids = [r.id for r in db.query(RecordModel.id).filter(RecordModel.source_id == int(source_id)).all()]
        q = q.filter(or_(MatchModel.record_a_id.in_(ids), MatchModel.record_b_id.in_(ids)))
    rows = q.order_by(MatchModel.confidence.desc()).all()
    counts = {"MATCH": 0, "POSSIBLE_MATCH": 0, "NO_MATCH": 0}
    for r in rows:
        d = (r.evidence or {}).get("decision")
        if d in counts:
            counts[d] += 1
    if decision:
        if decision not in ("MATCH", "POSSIBLE_MATCH", "NO_MATCH"):
            raise HTTPException(status_code=422, detail="decision must be MATCH, POSSIBLE_MATCH or NO_MATCH")
        rows = [r for r in rows if (r.evidence or {}).get("decision") == decision]
    total = len(rows)
    page_rows = rows[(page - 1) * limit: page * limit]
    return {"total": total, "page": page, "limit": limit, "mode": "live" if (job_id or source_id) else "all", "model_version": _msm.get_model_version(),
            "thresholds": {"MATCH": settings.MATCH_THRESHOLD, "POSSIBLE_MATCH": settings.POSSIBLE_MATCH_THRESHOLD},
            "counts": counts,
            "items": [{"id": r.id, "job": (r.entity_group_id or "").replace("job-", ""), "record_a_id": r.record_a_id, "record_b_id": r.record_b_id, "confidence": r.final_confidence if r.final_confidence is not None else r.confidence, "model_score": (r.evidence or {}).get("model_score", r.confidence), "match_score": (r.evidence or {}).get("model_score", r.confidence), "decision": (r.evidence or {}).get("decision"), "risk": r.risk or (r.evidence or {}).get("risk"), "auto_resolvable": r.auto_resolvable if r.auto_resolvable is not None else (r.evidence or {}).get("auto_resolvable"), "recommendation": r.recommendation or (r.evidence or {}).get("recommendation"), "verification_status": (r.evidence or {}).get("verification_status", "NEEDS_REVIEW"), "field_scores": (r.evidence or {}).get("field_scores"), "evidence": r.evidence, "model_version": (r.evidence or {}).get("model_version", _msm.get_model_version()), "created_at": r.created_at.isoformat() if r.created_at else None} for r in page_rows]}


@router.get("/matches/{match_id}")
def get_match_detail(match_id: int, db: Session = Depends(get_db)):
    from backend.app.services import model_service as _msd
    m = db.query(MatchModel).filter(MatchModel.id == match_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")
    ra = db.query(RecordModel).filter(RecordModel.id == m.record_a_id).first()
    rb = db.query(RecordModel).filter(RecordModel.id == m.record_b_id).first()
    job_id = (m.entity_group_id or "").replace("job-", "") or None
    job = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.id == int(job_id)).first() if job_id and str(job_id).isdigit() else None
    return {"id": m.id, "job_id": job.id if job else job_id, "mode": "live", "model_version": (m.evidence or {}).get("model_version", _msd.get_model_version()),
            "record_a": {"id": ra.id, "source_id": ra.source_id, "source_record_id": ra.source_record_id, "data": ra.data} if ra else None,
            "record_b": {"id": rb.id, "source_id": rb.source_id, "source_record_id": rb.source_record_id, "data": rb.data} if rb else None,
            "confidence": m.final_confidence if m.final_confidence is not None else m.confidence,
            "model_score": (m.evidence or {}).get("model_score", m.confidence),
            "match_score": (m.evidence or {}).get("model_score", m.confidence), "decision": (m.evidence or {}).get("decision"),
            "risk": m.risk or (m.evidence or {}).get("risk"),
            "risk_reason": (m.evidence or {}).get("risk_reason"),
            "auto_resolvable": m.auto_resolvable if m.auto_resolvable is not None else (m.evidence or {}).get("auto_resolvable"),
            "recommendation": m.recommendation or (m.evidence or {}).get("recommendation"),
            "verification_status": (m.evidence or {}).get("verification_status", "NEEDS_REVIEW"),
            "penalties": (m.evidence or {}).get("penalties"),
            "field_scores": (m.evidence or {}).get("field_scores"),
            "field_evidence": (m.evidence or {}).get("field_evidence"),
            "evidence": m.evidence,
            "job_status": job.status if job else None}


# ---------- Presence (Phase 5C: read-only; observations carry no directives) ----------

@router.get("/presence/observations")
def list_presence_observations(job_id: Optional[int] = Query(None), state: Optional[str] = Query(None), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    if state and state not in presence_svc.PRESENCE_STATES:
        raise HTTPException(status_code=422, detail=f"state must be one of {list(presence_svc.PRESENCE_STATES)}")
    q = db.query(PresenceObservationModel)
    if job_id:
        q = q.filter(PresenceObservationModel.job_id == job_id)
    if state:
        q = q.filter(PresenceObservationModel.record_presence == state)
    total = q.count()
    rows = q.order_by(PresenceObservationModel.id.asc()).offset((page - 1) * limit).limit(limit).all()
    return {"total": total, "page": page, "limit": limit,
            "items": [{"id": r.id, "job_id": r.job_id, "record_ref": r.record_ref,
                       "record_presence": r.record_presence, "entity_presence": r.entity_presence,
                       "basis": r.basis,
                       "explanation": presence_svc.explanation_for(r.record_presence, r.basis),
                       "scope": r.scope, "snapshot_a_ref": r.snapshot_a_ref,
                       "snapshot_b_ref": r.snapshot_b_ref,
                       "observed_at": r.observed_at.isoformat() if r.observed_at else None,
                       "pipeline_version": r.pipeline_version} for r in rows]}


@router.get("/presence/summary")
def presence_summary(job_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(PresenceObservationModel)
    if job_id:
        q = q.filter(PresenceObservationModel.job_id == job_id)
    counts = {s: 0 for s in presence_svc.PRESENCE_STATES}
    bases: Dict[str, int] = {}
    total = 0
    for (state, basis) in q.with_entities(PresenceObservationModel.record_presence, PresenceObservationModel.basis).all():
        if state in counts:
            counts[state] += 1
        bases[basis] = bases.get(basis, 0) + 1
        total += 1
    return {"job_id": job_id, "total": total, "counts": counts, "bases": bases}


def _presence_for_records(db, job_id, record_ids):
    """Read-only presence lookup scoped strictly to one comparison job.

    Returns {record_id: observation-dict-or-None}. Never invents states:
    no row in this job/scope → None. Never queries across jobs.
    """
    from backend.app.services import presence as _ps2
    out = {}
    for rid in record_ids:
        obs = None
        if job_id is not None and rid is not None:
            try:
                jid = int(job_id)
            except (TypeError, ValueError):
                jid = None
            if jid is not None:
                obs = db.query(PresenceObservationModel).filter(
                    PresenceObservationModel.job_id == jid,
                    PresenceObservationModel.record_ref == str(rid)).order_by(
                    PresenceObservationModel.id.desc()).first()
        out[rid] = ({"id": obs.id, "record_ref": obs.record_ref,
                     "record_presence": obs.record_presence, "entity_presence": obs.entity_presence,
                     "basis": obs.basis,
                     "explanation": _ps2.explanation_for(obs.record_presence, obs.basis),
                     "scope": obs.scope, "snapshot_a_ref": obs.snapshot_a_ref,
                     "snapshot_b_ref": obs.snapshot_b_ref,
                     "observed_at": obs.observed_at.isoformat() if obs.observed_at else None}
                    if obs is not None else None)
    return out


@router.get("/model/info")
def get_model_info():
    from backend.app.services import model_service as _ms4
    return {"mode": "model", **_ms4.get_model_metadata()}


@router.get("/stats/summary")
def stats_summary(job_id: Optional[int] = Query(None), source_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Persisted backend metrics for dashboards — never static, never cross-mode."""
    from backend.app.db.models import ResolutionLogModel
    mq = db.query(MatchModel)
    if job_id:
        mq = mq.filter(MatchModel.entity_group_id == f"job-{job_id}")
    if source_id and str(source_id).isdigit():
        ids = [r.id for r in db.query(RecordModel.id).filter(RecordModel.source_id == int(source_id)).all()]
        mq = mq.filter(or_(MatchModel.record_a_id.in_(ids), MatchModel.record_b_id.in_(ids)))
    matches = mq.all()
    mids = [m.id for m in matches]
    conf_q = db.query(ConflictModel)
    if mids and (job_id or source_id):
        conf_q = conf_q.filter(ConflictModel.match_id.in_(mids))
    elif job_id or source_id:
        conf_q = conf_q.filter(ConflictModel.id == -1)
    conflicts = conf_q.all()
    auto = sum(1 for m in matches if (m.evidence or {}).get("decision") == "MATCH" and bool((m.evidence or {}).get("auto_resolvable")))
    manual = sum(1 for m in matches if (m.evidence or {}).get("decision") in ("POSSIBLE_MATCH",) or ((m.evidence or {}).get("decision") == "MATCH" and not bool((m.evidence or {}).get("auto_resolvable"))))
    return {"mode": "live" if (job_id or source_id) else "all",
            "matches": sum(1 for m in matches if (m.evidence or {}).get("decision") == "MATCH"),
            "possible": sum(1 for m in matches if (m.evidence or {}).get("decision") == "POSSIBLE_MATCH"),
            "nomatch": sum(1 for m in matches if (m.evidence or {}).get("decision") == "NO_MATCH"),
            "auto_resolvable": auto, "manual_review": manual,
            "high_risk": sum(1 for c in conflicts if c.risk_level in ("HIGH", "CRITICAL")),
            "conflicts": len(conflicts),
            "resolved": sum(1 for c in conflicts if c.resolution_status in ("approved", "modified")),
            "rejected": sum(1 for c in conflicts if c.resolution_status == "rejected"),
            "deferred": sum(1 for c in conflicts if c.resolution_status == "deferred"),
            "sync_success": db.query(SyncJobModel).filter(SyncJobModel.status == "SUCCESS").count() if not (job_id or source_id) else 0,
            "sync_failed": db.query(SyncJobModel).filter(SyncJobModel.status == "FAILED").count() if not (job_id or source_id) else 0}


# LEGACY: superseded by POST /reconciliation + GET /jobs/{id}/results. Kept for backward compatibility; not product surface.
@router.post("/reconcile")
def run_reconciliation_legacy():
    engine = ReconciliationEngine()
    return engine.run_reconciliation([])


# ---------- Conflicts ----------

@router.get("/conflicts")
def list_conflicts(status: Optional[str] = Query(None), risk_level: Optional[str] = Query(None), risk: Optional[str] = Query(None), source_id: Optional[str] = Query(None), job_id: Optional[int] = Query(None), field: Optional[str] = Query(None), source: Optional[str] = Query(None), job: Optional[int] = Query(None), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    if risk and not risk_level:
        risk_level = risk
    if job and not job_id:
        job_id = job
    if source and not source_id and str(source).isdigit():
        source_id = source
    q = db.query(ConflictModel)
    if status:
        q = q.filter(ConflictModel.resolution_status == status)
    if risk_level:
        q = q.filter(ConflictModel.risk_level == risk_level)
    if job_id:
        mids = [m.id for m in db.query(MatchModel.id).filter(MatchModel.entity_group_id == f"job-{job_id}").all()]
        q = q.filter(ConflictModel.match_id.in_(mids)) if mids else q.filter(ConflictModel.id == -1)
    if source_id and str(source_id).isdigit():
        q = q.filter(or_(ConflictModel.record_a_id.in_(db.query(RecordModel.id).filter(RecordModel.source_id==int(source_id))), ConflictModel.record_b_id.in_(db.query(RecordModel.id).filter(RecordModel.source_id==int(source_id)))))
    rows = q.order_by(ConflictModel.id.desc()).all()
    if field:
        rows = [r for r in rows if any((f.get("field_name") == field) for f in (r.conflicting_fields or []))]
    total = len(rows)
    rows = rows[(page - 1) * limit: page * limit]
    out = []
    ignore_fields = {"id","entity_id","rec_id","customer_id","source_id","source_record_id","rec_a","rec_b","_id"}
    for r in rows:
        cfields = r.conflicting_fields or []
        fixed = []
        for f in cfields:
            if "field_name" in f:
                if f["field_name"] in ignore_fields or f["field_name"].startswith("_") or f["field_name"].startswith("?"):
                    continue
                fixed.append(f)
            elif "field" in f:
                if f.get("field") in ignore_fields:
                    continue
                fixed.append({"field_name": f.get("field"), "conflict_type": f.get("type") or f.get("conflict_type") or "mismatch", "values": f.get("values"), "sources": f.get("sources") or list(f.get("values", {}).keys()) if f.get("values") else []})
            else:
                fixed.append(f)
        # if all fields were ignored and we filtered everything, fetch actual record diff for meaningful display
        if not fixed and r.record_a_id and r.record_b_id:
            try:
                ra = db.query(RecordModel).filter(RecordModel.id==r.record_a_id).first()
                rb = db.query(RecordModel).filter(RecordModel.id==r.record_b_id).first()
                if ra and rb:
                    for k in set(list((ra.data or {}).keys()) + list((rb.data or {}).keys())):
                        if k in ignore_fields or k.startswith("_") or k.startswith("?"):
                            continue
                        va=(ra.data or {}).get(k); vb=(rb.data or {}).get(k)
                        if va != vb and str(va).strip() and str(vb).strip() and str(va).strip()!=str(vb).strip():
                            fixed.append({"field_name": k, "conflict_type": "mismatch", "values": {"a": va, "b": vb}, "sources": ["a","b"]})
                            if len(fixed)>=2:
                                break
            except: pass
        out.append({"id": r.id, "record_a_id": r.record_a_id, "record_b_id": r.record_b_id, "match_id": r.match_id, "conflicting_fields": fixed, "confidence": r.confidence, "risk_level": r.risk_level, "evidence": r.evidence, "recommendation": r.recommendation, "resolution_status": r.resolution_status, "auto_resolvable": r.auto_resolvable, "created_at": r.created_at.isoformat() if r.created_at else None})
    return out


@router.get("/conflicts/{conflict_id}")
def get_conflict(conflict_id: int, db: Session = Depends(get_db)):
    from backend.app.services import model_service as _msc
    m = db.query(ConflictModel).filter(ConflictModel.id == conflict_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Conflict not found")
    cfields = m.conflicting_fields or []
    fixed = []
    for f in cfields:
        if "field_name" in f:
            fixed.append(f)
        elif "field" in f:
            fixed.append({"field_name": f.get("field"), "conflict_type": f.get("type") or "mismatch", "values": f.get("values"), "sources": list(f.get("values", {}).keys()) if f.get("values") else []})
        else:
            fixed.append(f)
    match = db.query(MatchModel).filter(MatchModel.id == m.match_id).first() if m.match_id else None
    ra = db.query(RecordModel).filter(RecordModel.id == m.record_a_id).first()
    rb = db.query(RecordModel).filter(RecordModel.id == m.record_b_id).first()
    job_id = ((match.entity_group_id or "") if match else (m.evidence or {}).get("job_id", "") or "")
    job_id = str(job_id).replace("job-", "") if job_id else None
    job = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.id == int(job_id)).first() if job_id and str(job_id).isdigit() else None
    ev = m.evidence or {}
    _jid = job.id if job else (int(job_id) if job_id and str(job_id).isdigit() else None)
    _pres = _presence_for_records(db, _jid, [m.record_a_id, m.record_b_id])
    return {"id": m.id, "mode": "live", "model_version": ev.get("model_version", _msc.get_model_version()),
            "job_id": job.id if job else (int(job_id) if job_id and str(job_id).isdigit() else None),
            "job_status": job.status if job else None,
            "match": {"id": match.id, "confidence": match.confidence, "decision": (match.evidence or {}).get("decision"), "field_scores": (match.evidence or {}).get("field_scores"), "evidence": match.evidence} if match else None,
            "entity": {"record_a_id": m.record_a_id, "record_b_id": m.record_b_id},
            "source_record": {"id": ra.id, "source_id": ra.source_id, "source_record_id": ra.source_record_id, "data": ra.data} if ra else None,
            "target_record": {"id": rb.id, "source_id": rb.source_id, "source_record_id": rb.source_record_id, "data": rb.data} if rb else None,
            "field": (fixed[0] or {}).get("field_name") if fixed else None,
            "field_values": (fixed[0] or {}).get("values") if fixed else None,
            "record_a_id": m.record_a_id, "record_b_id": m.record_b_id, "match_id": m.match_id, "conflicting_fields": fixed,
            "confidence": m.confidence, "match_confidence": match.confidence if match else m.confidence,
            "field_similarity": ev.get("field_scores"), "recommendation": m.recommendation,
            "reason": ev.get("conflict_reason"), "risk": m.risk_level, "risk_level": m.risk_level, "risk_reason": ev.get("risk_reason"),
            "status": m.resolution_status, "resolution_status": m.resolution_status, "auto_resolvable": m.auto_resolvable,
            "evidence": ev, "created_at": m.created_at.isoformat() if m.created_at else None,
            "presence": {"record_a": _pres.get(m.record_a_id), "record_b": _pres.get(m.record_b_id)}}


@router.post("/conflicts/{conflict_id}/resolve", response_model=ResolutionResponse)
def resolve_conflict(conflict_id: int, req: ResolutionRequest, db: Session = Depends(get_db)):
    from backend.app.services import resolution as _rs
    m = db.query(ConflictModel).filter(ConflictModel.id == conflict_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Conflict not found")
    try:
        row, created = _rs.resolve_conflict(db, m, req.action, req.modified_values, getattr(req, "reason", None))
    except _rs.ResolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    try:
        status = _rs.STATUS_FOR[_rs.CANONICAL[req.action]]
    except KeyError:
        raise HTTPException(status_code=422, detail=f"Invalid action '{req.action}'")
    note = "" if created else " (already applied — idempotent)"
    return ResolutionResponse(conflict_id=conflict_id, status=status, message=f"Conflict {conflict_id} {status}{note}", resolved_at=m.resolved_at)


@router.get("/conflicts/{conflict_id}/resolutions")
def list_resolutions(conflict_id: int, db: Session = Depends(get_db)):
    from backend.app.db.models import ResolutionLogModel
    import json as _json
    if not db.query(ConflictModel).filter(ConflictModel.id == conflict_id).first():
        raise HTTPException(status_code=404, detail="Conflict not found")
    rows = db.query(ResolutionLogModel).filter(ResolutionLogModel.conflict_id == conflict_id).order_by(ResolutionLogModel.id).all()
    out = []
    for r in rows:
        try:
            payload = _json.loads(r.detail or "{}")
        except Exception:
            payload = {"raw": r.detail}
        out.append({"id": r.id, "conflict_id": r.conflict_id, "action": payload.get("canonical", r.action),
                    "selected_source": payload.get("selected_source"), "previous_value": payload.get("previous_value"),
                    "resolved_value": payload.get("resolved_value"), "reason": payload.get("reason"),
                    "status": r.action, "resolved_by": r.resolved_by, "created_at": r.created_at.isoformat() if r.created_at else None})
    return out


@router.get("/conflicts/{conflict_id}/audit")
def conflict_audit(conflict_id: int, db: Session = Depends(get_db)):
    from backend.app.db.models import ResolutionLogModel, SyncJobModel
    if not db.query(ConflictModel).filter(ConflictModel.id == conflict_id).first():
        raise HTTPException(status_code=404, detail="Conflict not found")
    res_ids = [r.id for r in db.query(ResolutionLogModel.id).filter(ResolutionLogModel.conflict_id == conflict_id).all()]
    sync_ids = [s.id for s in db.query(SyncJobModel.id).filter(SyncJobModel.resolution_id.in_(res_ids)).all()] if res_ids else []
    q = db.query(AuditLogModel).filter(
        ((AuditLogModel.entity_type == "conflict") & (AuditLogModel.entity_id == str(conflict_id))) |
        ((AuditLogModel.entity_type == "resolution") & (AuditLogModel.entity_id.in_([str(i) for i in res_ids]))) |
        ((AuditLogModel.entity_type == "sync_job") & (AuditLogModel.entity_id.in_([str(i) for i in sync_ids])))
    ) if (res_ids or sync_ids) else db.query(AuditLogModel).filter((AuditLogModel.entity_type == "conflict") & (AuditLogModel.entity_id == str(conflict_id)))
    rows = q.order_by(AuditLogModel.created_at).all()
    return [{"id": r.id, "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
             "details": r.details, "error": r.error, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.post("/resolutions/{resolution_id}/dry-run")
def resolution_dry_run(resolution_id: int, db: Session = Depends(get_db)):
    from backend.app.services import resolution as _rs
    try:
        job, created = _rs.dry_run_resolution(db, resolution_id)
    except _rs.ResolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    meta = job.response_metadata or {}
    return {"sync_job_id": job.id, "resolution_id": resolution_id, "destination": job.destination,
            "field": job.field_name, "current_value": meta.get("current_value"), "proposed_value": meta.get("proposed_value"),
            "operation": "UPDATE", "status": job.status, "result": "DRY RUN SUCCESS — destination NOT modified",
            "already_existed": not created}


@router.post("/resolutions/{resolution_id}/push")
def resolution_push(resolution_id: int, payload: Dict[str, Any], db: Session = Depends(get_db)):
    from backend.app.services import resolution as _rs
    try:
        job, executed = _rs.push_resolution(db, resolution_id, bool(payload.get("confirm")), payload.get("simulate_error"))
    except _rs.ResolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    meta = job.response_metadata or {}
    return {"sync_job_id": job.id, "resolution_id": resolution_id, "destination": job.destination,
            "status": job.status, "verified": meta.get("verified", False), "mock": bool(meta.get("mock", False)),
            "already_applied": not executed,
            "result": "ALREADY_APPLIED — no duplicate write" if not executed else f"PUSH {job.status}",
            "error": job.error_message, "attempt_count": job.attempt_count}


@router.get("/sync-jobs/{sync_job_id}")
def get_sync_job(sync_job_id: int, db: Session = Depends(get_db)):
    from backend.app.db.models import SyncAttemptModel
    from backend.app.services import resolution as _rs
    job = db.query(SyncJobModel).filter(SyncJobModel.id == sync_job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")
    attempts = db.query(SyncAttemptModel).filter(SyncAttemptModel.job_id == job.id).order_by(SyncAttemptModel.attempt_number).all()
    return {"id": job.id, "resolution_id": job.resolution_id, "destination": job.destination, "operation": job.operation,
            "field": job.field_name, "resolved_value": job.resolved_value, "status": job.status, "progress": job.progress,
            "attempt_count": job.attempt_count, "error": job.error_message, "response_metadata": job.response_metadata,
            "idempotency_key": job.idempotency_key,
            "review": _rs.sync_review_status(job),
            "attempts": [{"n": a.attempt_number, "status": a.status, "error": a.error_message} for a in attempts],
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None}


@router.post("/sync-jobs/{sync_job_id}/retry")
def retry_sync_job(sync_job_id: int, payload: Dict[str, Any], db: Session = Depends(get_db)):
    from backend.app.services import resolution as _rs
    try:
        job, _ = _rs.retry_sync(db, sync_job_id, (payload or {}).get("simulate_error"))
    except _rs.ResolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return {"sync_job_id": job.id, "status": job.status, "attempt_count": job.attempt_count, "error": job.error_message}


@router.post("/conflicts/{conflict_id}/reject", response_model=ResolutionResponse)
def reject_conflict(conflict_id: int, db: Session = Depends(get_db)):
    return resolve_conflict(conflict_id, ResolutionRequest(action="reject"), db)


# ---------- Schemas ----------

@router.get("/schemas", response_model=List[Schema])
def list_schemas(db: Session = Depends(get_db)):
    rows = db.query(SchemaModel).all()
    return [{"id": r.id, "source_id": str(r.source_id), "fields": r.fields, "field_count": r.field_count, "version": r.version, "created_at": r.created_at} for r in rows]


@router.get("/schemas/drift")
def detect_schema_drift(source_id: str = Query(...), db: Session = Depends(get_db)):
    from backend.app.services import schema_analyzer as _sa
    if not str(source_id).isdigit():
        raise HTTPException(status_code=422, detail="source_id must be numeric")
    versions = db.query(SchemaModel).filter(SchemaModel.source_id == int(source_id)).order_by(SchemaModel.version.desc()).limit(2).all()
    if len(versions) < 2:
        return {"source_id": source_id, "status": "insufficient_history", "versions": len(versions),
                "drifts": [], "message": "Upload a second file to this source to detect drift"}
    new_v, old_v = versions[0], versions[1]
    drifts = _sa.compare_schemas(old_v.fields or [], new_v.fields or [])
    worst = "BLOCKING" if any(d.get("severity") == "BLOCKING" for d in drifts) else ("WARNING" if drifts else "SAFE")
    handling = ("New uploads still process, but matching on removed/renamed identifiers is degraded — remap columns or confirm rename." if worst == "BLOCKING"
                else "Review changes; matching continues." if worst == "WARNING" else "No action needed.")
    return {"source_id": source_id, "status": "compared", "from_version": old_v.version, "to_version": new_v.version,
            "drifts": drifts, "total_changes": len(drifts), "worst_severity": worst,
            "what": [f"{d['change']}: {d.get('field', d.get('old_name', '') + '→' + d.get('new_name', ''))}" for d in drifts],
            "why": [d.get("why", "") for d in drifts], "handling": handling}


# ---------- Jobs ----------

@router.post("/jobs", response_model=Job)
def create_job(job: JobCreate, db: Session = Depends(get_db)):
    key = job.idempotency_key or hashlib.sha256(f"{job.job_type}:{job.source_id}".encode()).hexdigest()[:32]
    existing = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.idempotency_key == key).first()
    if existing:
        return Job(id=existing.id, job_type=existing.job_type, status=StatusEnum(existing.status), progress=existing.progress)
    model = ReconciliationJobModel(job_type=job.job_type, source_id=job.source_id, idempotency_key=key)
    db.add(model)
    try:
        db.commit()
        db.refresh(model)
    except IntegrityError:
        db.rollback()
        existing = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.idempotency_key == key).first()
        return Job(id=existing.id, job_type=existing.job_type, status=StatusEnum(existing.status), progress=existing.progress)
    return Job(id=model.id, job_type=model.job_type, status=StatusEnum(model.status), progress=model.progress)


@router.get("/jobs")
def list_jobs(status_q: Optional[str] = Query(None, alias="status"), source_id: Optional[str] = Query(None), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    q = db.query(ReconciliationJobModel)
    if status_q:
        q = q.filter(ReconciliationJobModel.status == status_q)
    if source_id and str(source_id).isdigit():
        q = q.filter(ReconciliationJobModel.source_id.contains(str(source_id)))
    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": [{"id": j.id, "job_type": j.job_type, "status": j.status, "progress": j.progress, "created_at": j.created_at, "source_id": j.source_id} for j in items]}


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: int, db: Session = Depends(get_db)):
    m = db.query(ReconciliationJobModel).filter(ReconciliationJobModel.id == job_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(job_id=m.id, status=StatusEnum(m.status), progress=m.progress, message=m.error_message or "Job pending")


# ---------- Matching (live) ----------

# LEGACY: superseded by GET /matches. Kept for backward compatibility; not product surface.
@router.get("/match")
def find_matches(threshold: float = Query(settings.MATCH_THRESHOLD, ge=0.0, le=1.0), limit: int = Query(100, ge=1, le=500), source_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    # isolate live dataset: if source_id provided, filter to that source only (live), else use all (benchmark)
    q = db.query(RecordModel)
    if source_id and str(source_id).isdigit():
        q = q.filter(RecordModel.source_id == int(source_id))
    records = q.limit(limit).all()
    dicts = []
    for r in records:
        d = r.normalized_data or r.data or {}
        d = dict(d)
        d["id"] = r.id
        if "name" not in d and "given_name" in d:
            d["name"] = f"{d.get('given_name','')} {d.get('surname','')}".strip()
        if "external_id" not in d and "soc_sec_id" in d:
            d["external_id"] = str(d["soc_sec_id"])
        dicts.append(d)
    engine = MatchingEngine(use_ml=True)
    matches = engine.find_matches(dicts, threshold=threshold)
    return {"total_records": len(dicts), "threshold": threshold, "source_id": source_id, "matches": [m.model_dump() if hasattr(m, "model_dump") else m.dict() for m in matches], "model": "ml" if engine.use_ml else "rule"}


# LEGACY: superseded by POST /reconciliation. Kept for backward compatibility; not product surface.
@router.post("/matching/run")
def run_matching(payload: Dict[str, Any], db: Session = Depends(get_db)):
    threshold = float(payload.get("threshold", settings.MATCH_THRESHOLD))
    limit = int(payload.get("limit", 200))
    engine = MatchingEngine(rules=payload.get("rules"))
    records = db.query(RecordModel).limit(limit).all()
    dicts = []
    for r in records:
        d = r.normalized_data or r.data or {}
        d = dict(d)
        d["id"] = r.id
        if "external_id" not in d and "soc_sec_id" in d:
            d["external_id"] = str(d["soc_sec_id"])
        dicts.append(d)
    matches = engine.find_matches(dicts, threshold=threshold)
    groups = engine.find_entity_groups(dicts, threshold=threshold)
    return {"threshold": threshold, "total_records": len(dicts), "matches": [m.model_dump() if hasattr(m, "model_dump") else m.dict() for m in matches], "groups": [g.model_dump() if hasattr(g, "model_dump") else g.dict() for g in groups]}


@router.get("/entity-groups")
def find_entity_groups(threshold: float = Query(settings.MATCH_THRESHOLD, ge=0.0, le=1.0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    engine = MatchingEngine()
    records = db.query(RecordModel).limit(limit).all()
    dicts = [{"id": r.id, **(r.normalized_data or r.data or {})} for r in records]
    return engine.find_entity_groups(dicts, threshold=threshold)


# ---------- Audit ----------

@router.get("/audit-logs")
def get_audit_logs(request_id: Optional[str] = None, job_id: Optional[str] = None, source_id: Optional[str] = Query(None), limit: int = Query(20, ge=1, le=100), page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    from backend.app.db.models import ResolutionLogModel
    q = db.query(AuditLogModel)
    if request_id:
        q = q.filter(AuditLogModel.request_id == request_id)
    scope = None
    if job_id and str(job_id).isdigit():
        # server-side lineage expansion: job -> matches -> conflicts -> resolutions -> syncs
        mids = [m.id for m in db.query(MatchModel.id).filter(MatchModel.entity_group_id == f"job-{job_id}").all()]
        cids = [c.id for c in db.query(ConflictModel.id).filter(ConflictModel.match_id.in_(mids)).all()] if mids else []
        rids = [r.id for r in db.query(ResolutionLogModel.id).filter(ResolutionLogModel.conflict_id.in_(cids)).all()] if cids else []
        sids = [s.id for s in db.query(SyncJobModel.id).filter(SyncJobModel.resolution_id.in_(rids)).all()] if rids else []
        conds = [AuditLogModel.job_id == int(job_id)]
        if cids:
            conds.append((AuditLogModel.entity_type == "conflict") & (AuditLogModel.entity_id.in_([str(i) for i in cids])))
        if rids:
            conds.append((AuditLogModel.entity_type == "resolution") & (AuditLogModel.entity_id.in_([str(i) for i in rids])))
        if sids:
            conds.append((AuditLogModel.entity_type == "sync_job") & (AuditLogModel.entity_id.in_([str(i) for i in sids])))
        q = q.filter(or_(*conds))
        scope = {"mode": "live", "job_id": int(job_id)}
    elif source_id and str(source_id).isdigit():
        rec_ids = [r.id for r in db.query(RecordModel.id).filter(RecordModel.source_id == int(source_id)).all()]
        cids = [c.id for c in db.query(ConflictModel.id).filter(or_(ConflictModel.record_a_id.in_(rec_ids), ConflictModel.record_b_id.in_(rec_ids))).all()] if rec_ids else []
        rids = [r.id for r in db.query(ResolutionLogModel.id).filter(ResolutionLogModel.conflict_id.in_(cids)).all()] if cids else []
        sids = [s.id for s in db.query(SyncJobModel.id).filter(SyncJobModel.resolution_id.in_(rids)).all()] if rids else []
        conds = [AuditLogModel.source_id == str(source_id)]
        if cids:
            conds.append((AuditLogModel.entity_type == "conflict") & (AuditLogModel.entity_id.in_([str(i) for i in cids])))
        if rids:
            conds.append((AuditLogModel.entity_type == "resolution") & (AuditLogModel.entity_id.in_([str(i) for i in rids])))
        if sids:
            conds.append((AuditLogModel.entity_type == "sync_job") & (AuditLogModel.entity_id.in_([str(i) for i in sids])))
        q = q.filter(or_(*conds))
        scope = {"mode": "live", "source_id": int(source_id)}
    total = q.count()
    items = q.order_by(AuditLogModel.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": items, "scope": scope or {"mode": "all"}}


@router.get("/audit")
def get_audit_legacy(limit: int = Query(100, ge=1, le=1000)):
    audit = AuditService()
    return audit.get_logs(limit=limit)


# ---------- Connectors validate ----------

@router.get("/connectors/csv/validate")
def validate_csv(source: str):
    return CSVConnector().validate(source)


@router.get("/connectors/json/validate")
def validate_json(source: str):
    return JSONConnector().validate(source)


@router.get("/connectors/rest/validate")
def validate_rest(endpoint: str):
    return RESTConnector().validate(endpoint)
