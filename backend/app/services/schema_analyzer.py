"""Schema analysis and drift detection service."""
from typing import Any, Dict, List, Optional
from backend.app.core.logging import logger
from backend.app.services.normalization import normalize_date
from backend.app.schemas.sources import SchemaField, SchemaDrift, SchemaDriftReport
from backend.app.schemas.base import SourceType


class SchemaAnalyzer:
    def __init__(self):
        self.schemas: Dict[str, List[SchemaField]] = {}

    def register_schema(self, source_id: str, fields: List[Dict[str, Any]]) -> None:
        schema_fields = [SchemaField(**f) if isinstance(f, dict) else f for f in fields]
        self.schemas[source_id] = schema_fields
        logger.info("Schema registered", source_id=source_id, field_count=len(schema_fields))

    def detect_drift(self, source_id: str, schema_id_a: int, schema_id_b: int,
                     fields_a: List[SchemaField], fields_b: List[SchemaField]) -> SchemaDriftReport:
        def parse(f: Any) -> SchemaField:
            return SchemaField(**f) if isinstance(f, dict) else f
        fields_a = [parse(f) for f in fields_a]
        fields_b = [parse(f) for f in fields_b]
        map_a = {f.name: f for f in fields_a}
        map_b = {f.name: f for f in fields_b}
        drifts: List[SchemaDrift] = []

        all_names = set(map_a.keys()) | set(map_b.keys())
        for name in all_names:
            if name not in map_a:
                drifts.append(SchemaDrift(
                    field_name=name,
                    change_type="added",
                    new_type=map_b[name].data_type,
                    confidence=0.9,
                ))
            elif name not in map_b:
                drifts.append(SchemaDrift(
                    field_name=name,
                    change_type="removed",
                    old_type=map_a[name].data_type,
                    confidence=0.9,
                ))
            elif map_a[name].data_type != map_b[name].data_type:
                drifts.append(SchemaDrift(
                    field_name=name,
                    change_type="type_changed",
                    old_type=map_a[name].data_type,
                    new_type=map_b[name].data_type,
                    confidence=0.95,
                ))

        total_changes = len(drifts)
        report = SchemaDriftReport(
            source_id=source_id,
            schema_id_a=schema_id_a,
            schema_id_b=schema_id_b,
            drifts=drifts,
            total_changes=total_changes,
        )
        logger.info("Schema drift detected", source_id=source_id, changes=total_changes)
        return report

    def analyze_schema(self, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        parsed = [SchemaField(**f) if isinstance(f, dict) else f for f in fields]
        data_types: Dict[str, int] = {}
        nullable_count = 0
        unique_count = 0
        for field in parsed:
            data_types[field.data_type] = data_types.get(field.data_type, 0) + 1
            if field.nullable:
                nullable_count += 1
            if field.unique:
                unique_count += 1

        analysis = {
            "field_count": len(parsed),
            "data_type_distribution": data_types,
            "nullable_ratio": nullable_count / len(parsed) if parsed else 0,
            "unique_fields": unique_count,
            "has_timestamps": any(f.data_type == "datetime" for f in parsed),
            "completeness_score": round((len(parsed) - nullable_count) / len(parsed), 4) if parsed else 0,
        }
        logger.info("Schema analyzed", **analysis)
        return analysis

    def validate_record(self, source_id: str, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        errors = []
        if source_id not in self.schemas:
            return [{"error": "schema_not_found", "source_id": source_id}]
        schema_fields = self.schemas[source_id]
        schema_map = {f.name: f for f in schema_fields}
        for field_name, field_def in schema_map.items():
            if field_def.unique and field_name in record:
                pass
            if field_def.nullable is False and field_name not in record:
                errors.append({"field": field_name, "error": "missing_required", "data_type": field_def.data_type})
        return errors


REQUIRED_IDENTIFIERS = {"email", "phone", "external_id", "soc_sec_id", "customer_id", "rec_id", "id"}


def _is_required(field: Dict[str, Any]) -> bool:
    if "required" in field:
        return bool(field["required"])
    return field.get("name") in REQUIRED_IDENTIFIERS


def _strict_datetime(value: Any) -> Optional[str]:
    """Validator (not normalizer): canonical YYYY-MM-DD or None.

    `normalize_date` must NOT be used here — it returns unparseable input
    unchanged, so `is not None` is always true for strings (the Phase 5A bug
    that classified 'DOUGLAS ABBOTT' as datetime). Ambiguous day/month forms
    resolve month-first, matching the existing `normalize_date` format order;
    documented, not guessed per value."""
    from datetime import datetime as _dt
    if value is None:
        return None
    if isinstance(value, _dt):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if not s:
        return None
    try:
        return _dt.fromisoformat(s).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y",
                "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return _dt.strptime(s, fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 8 and not any(c.isalpha() for c in s):
        try:
            return _dt.strptime(digits, "%Y%m%d").strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return None
    return None


def infer_type(values: List[Any]) -> str:
    seen = [v for v in values if v is not None and not (isinstance(v, str) and not v.strip())]
    if not seen:
        return "string"
    if all(isinstance(v, bool) for v in seen):
        return "boolean"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in seen):
        return "integer"
    nums = 0
    for v in seen:
        try:
            float(str(v).strip())
            nums += 1
        except (ValueError, TypeError):
            pass
    if nums == len(seen):
        return "float" if any(isinstance(v, float) or "." in str(v) for v in seen) else "integer"
    # Datetime requires EVIDENCE: at least 80% of values must strictly parse.
    # A lone date-like value in a text column (or pure prose) stays string.
    parsed = sum(1 for v in seen if _strict_datetime(v) is not None)
    if parsed and parsed / len(seen) >= 0.8:
        return "datetime"
    return "string"


def infer_schema(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cols: Dict[str, List[Any]] = {}
    for r in records:
        for k, v in r.items():
            cols.setdefault(k, []).append(v)
    out = []
    for name, vals in cols.items():
        missing = sum(1 for v in vals if v is None or (isinstance(v, str) and not v.strip()))
        out.append({"name": name, "data_type": infer_type(vals), "nullable": missing > 0,
                    "required": name in REQUIRED_IDENTIFIERS})
    return out


def compare_schemas(expected: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect ADDED_COLUMN, REMOVED_COLUMN, POSSIBLE_RENAMED_COLUMN, TYPE_CHANGED,
    NULLABILITY_CHANGED with SAFE/WARNING/BLOCKING severity. Rename is a possibility."""
    from rapidfuzz import fuzz as _fuzz
    exp = {f["name"]: f for f in expected}
    inc = {f["name"]: f for f in incoming}
    drifts: List[Dict[str, Any]] = []
    removed = [n for n in exp if n not in inc]
    added = [n for n in inc if n not in exp]
    pairs = []
    for r in removed:
        best, score = None, 0
        for a in added:
            s = _fuzz.ratio(r.lower(), a.lower())
            if s > score:
                best, score = a, s
        if best and score >= 85:
            pairs.append((r, best, score))
    paired_r = {r for r, _, _ in pairs}
    paired_a = {a for _, a, _ in pairs}
    for r, a, s in pairs:
        sev = "BLOCKING" if (_is_required(exp[r]) or a in REQUIRED_IDENTIFIERS) else "WARNING"
        drifts.append({"change": "POSSIBLE_RENAMED_COLUMN", "old_name": r, "new_name": a,
                       "confidence": round(s / 100, 2), "severity": sev,
                       "why": f"'{r}' looks like '{a}' (similarity {s}); required-field rename breaks matching" if sev == "BLOCKING" else f"'{r}' may have been renamed to '{a}'"})
    for n in removed:
        if n in paired_r:
            continue
        sev = "BLOCKING" if _is_required(exp[n]) else "WARNING"
        drifts.append({"change": "REMOVED_COLUMN", "field": n, "old_type": exp[n].get("data_type"), "severity": sev,
                       "why": f"required identifier '{n}' removed — matching degrades" if sev == "BLOCKING" else f"column '{n}' removed"})
    for n in added:
        if n in paired_a:
            continue
        drifts.append({"change": "ADDED_COLUMN", "field": n, "new_type": inc[n].get("data_type"), "severity": "SAFE",
                       "why": f"new optional column '{n}' — ignored by matching"})
    for n in set(exp) & set(inc):
        if exp[n].get("data_type") != inc[n].get("data_type"):
            sev = "BLOCKING" if _is_required(exp[n]) else "WARNING"
            drifts.append({"change": "TYPE_CHANGED", "field": n, "old_type": exp[n].get("data_type"), "new_type": inc[n].get("data_type"),
                           "severity": sev, "why": f"type of '{n}' changed"})
        if exp[n].get("nullable") != inc[n].get("nullable") and not inc[n].get("nullable"):
            drifts.append({"change": "NULLABILITY_CHANGED", "field": n, "severity": "WARNING",
                           "why": f"'{n}' became non-nullable"})
    order = {"BLOCKING": 0, "WARNING": 1, "SAFE": 2}
    drifts.sort(key=lambda d: order.get(d["severity"], 3))
    return drifts