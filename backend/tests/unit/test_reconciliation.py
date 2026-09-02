"""Unit tests for reconciliation service."""
import pytest
from backend.app.services.reconciliation import ReconciliationEngine


class TestReconciliationEngine:
    def test_detect_conflicts_no_conflict(self):
        engine = ReconciliationEngine()
        record_a = {"name": "John", "age": 30}
        record_b = {"name": "John", "age": 30}
        conflicts = engine.detect_conflicts(record_a, record_b)
        assert len(conflicts) == 0

    def test_detect_conflicts_with_mismatch(self):
        engine = ReconciliationEngine()
        record_a = {"name": "John", "age": 30}
        record_b = {"name": "Jane", "age": 25}
        conflicts = engine.detect_conflicts(record_a, record_b)
        assert len(conflicts) >= 1

    def test_assess_risk_no_conflicts(self):
        engine = ReconciliationEngine()
        assert engine.assess_risk([]) == pytest.importorskip('backend.app.schemas.base').RiskLevel.LOW

    def test_auto_resolve_single_conflict(self):
        engine = ReconciliationEngine()
        conflicts = [pytest.importorskip('backend.app.schemas.conflicts').ConflictField(field_name="age", values={"a": 30, "b": 31}, sources=["a", "b"], conflict_type="mismatch")]
        assert engine.auto_resolve(conflicts) is True

    def test_run_reconciliation_empty(self):
        engine = ReconciliationEngine()
        result = engine.run_reconciliation([])
        assert result["total_records"] == 0
        assert result["processed_records"] == 0
        assert result["entity_groups"] == 0