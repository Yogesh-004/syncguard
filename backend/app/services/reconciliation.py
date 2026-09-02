"""Reconciliation engine service."""
from typing import Any, Dict, List, Optional
from backend.app.core.logging import logger
from backend.app.services.matching import MatchingEngine
from backend.app.schemas.conflicts import Conflict, ConflictField, ResolutionStatus
from backend.app.schemas.matching import EntityGroup
from backend.app.schemas.base import RiskLevel


class ReconciliationEngine:
    def __init__(self, matching_engine: Optional[MatchingEngine] = None):
        self.matching_engine = matching_engine or MatchingEngine()

    def detect_conflicts(self, record_a: Dict[str, Any], record_b: Dict[str, Any]) -> List[ConflictField]:
        conflicts = []
        all_keys = set(record_a.keys()) | set(record_b.keys())
        for key in all_keys:
            val_a = record_a.get(key)
            val_b = record_b.get(key)
            if val_a is None and val_b is None:
                continue
            if val_a == val_b:
                continue
            if val_a is None or val_b is None:
                conflicts.append(ConflictField(
                    field_name=key,
                    values={"record_a": val_a, "record_b": val_b},
                    sources=["source_a", "source_b"],
                    conflict_type="missing",
                ))
            elif isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                if abs(val_a - val_b) > 0.01:
                    conflicts.append(ConflictField(
                        field_name=key,
                        values={"record_a": val_a, "record_b": val_b},
                        sources=["source_a", "source_b"],
                        conflict_type="mismatch",
                    ))
            elif str(val_a) != str(val_b):
                conflicts.append(ConflictField(
                    field_name=key,
                    values={"record_a": val_a, "record_b": val_b},
                    sources=["source_a", "source_b"],
                    conflict_type="mismatch",
                ))
        logger.info("Conflicts detected", count=len(conflicts))
        return conflicts

    def assess_risk(self, conflicts: List[ConflictField]) -> RiskLevel:
        if not conflicts:
            return RiskLevel.LOW
        critical_count = sum(1 for c in conflicts if c.conflict_type == "type_error")
        if critical_count >= 3:
            return RiskLevel.CRITICAL
        if critical_count >= 1:
            return RiskLevel.HIGH
        high_count = sum(1 for c in conflicts if len(str(c.values)) > 100)
        if high_count >= 2:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM

    def auto_resolve(self, conflicts: List[ConflictField]) -> bool:
        for conflict in conflicts:
            if conflict.conflict_type == "type_error":
                return False
        return len(conflicts) <= 1

    def resolve_conflict(self, record_a: Dict[str, Any], record_b: Dict[str, Any],
                         action: str = "approve", modified_values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        conflicts = self.detect_conflicts(record_a, record_b)
        risk = self.assess_risk(conflicts)
        auto = self.auto_resolve(conflicts)

        if action == "approve" and auto:
            resolved = {**record_b}
            if modified_values:
                resolved.update(modified_values)
            return {
                "resolved_data": resolved,
                "conflicts": conflicts,
                "risk_level": risk.value,
                "resolution": "auto_approved" if auto else "manually_approved",
            }
        elif action == "reject":
            return {
                "resolved_data": None,
                "conflicts": conflicts,
                "risk_level": risk.value,
                "resolution": "rejected",
            }
        elif action == "modify" and modified_values:
            return {
                "resolved_data": modified_values,
                "conflicts": conflicts,
                "risk_level": risk.value,
                "resolution": "modified",
            }
        else:
            return {
                "resolved_data": None,
                "conflicts": conflicts,
                "risk_level": risk.value,
                "resolution": "deferred",
            }

    def run_reconciliation(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        entity_groups = self.matching_engine.find_entity_groups(records)
        conflicts_list = []
        resolutions = []

        for group in entity_groups:
            group_records = [r for r in records if r.get("id") in group.record_ids]
            if len(group_records) < 2:
                continue
            for i in range(len(group_records)):
                for j in range(i + 1, len(group_records)):
                    result = self.resolve_conflict(group_records[i], group_records[j])
                    if result["conflicts"]:
                        conflicts_list.append({
                            "record_a_id": group_records[i].get("id"),
                            "record_b_id": group_records[j].get("id"),
                            "conflicts": result["conflicts"],
                            "risk_level": result["risk_level"],
                        })
                    resolutions.append(result)

        total = len(records)
        processed = len(set(r.get("id") for r in records))
        result = {
            "total_records": total,
            "processed_records": processed,
            "entity_groups": len(entity_groups),
            "conflicts_found": len(conflicts_list),
            "resolutions": resolutions,
            "status": "completed" if not conflicts_list else "conflicts_detected",
        }
        logger.info("Reconciliation completed", **result)
        return result