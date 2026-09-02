"""Unit tests for schema analyzer."""
import pytest
from backend.app.services.schema_analyzer import SchemaAnalyzer


class TestSchemaAnalyzer:
    def test_analyze_schema(self):
        analyzer = SchemaAnalyzer()
        fields = [
            {"name": "id", "data_type": "integer", "nullable": False, "unique": True},
            {"name": "name", "data_type": "string", "nullable": True},
        ]
        result = analyzer.analyze_schema(fields)
        assert result["field_count"] == 2
        assert result["unique_fields"] == 1

    def test_validate_record_missing_field(self):
        analyzer = SchemaAnalyzer()
        analyzer.register_schema("test", [{"name": "id", "data_type": "integer", "nullable": False}])
        errors = analyzer.validate_record("test", {"name": "John"})
        assert len(errors) > 0
        assert errors[0]["field"] == "id"

    def test_detect_drift_added_field(self):
        analyzer = SchemaAnalyzer()
        fields_a = [{"name": "id", "data_type": "integer"}]
        fields_b = [{"name": "id", "data_type": "integer"}, {"name": "name", "data_type": "string"}]
        report = analyzer.detect_drift("source1", 1, 2, fields_a, fields_b)
        assert report.total_changes == 1