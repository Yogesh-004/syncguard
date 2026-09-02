"""Schema analysis and drift detection service."""
from typing import Any, Dict, List, Optional
from backend.app.core.logging import logger
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