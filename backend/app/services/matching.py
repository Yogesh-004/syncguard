"""Matching and entity resolution service — now ML-driven with trained production models."""
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import pickle
from rapidfuzz import fuzz
from backend.app.core.logging import logger
from backend.app.schemas.matching import MatchResult, MatchingRule, EntityGroup


def _load_ml_model(name="febrl3_ml.pkl"):
    p = Path(__file__).resolve().parents[1] / "models" / name
    if p.exists():
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.error("Failed to load ML model", error=str(e))
    return None

_ML_MODEL = _load_ml_model()
_ML_META = None
try:
    import json
    meta_p = Path(__file__).resolve().parents[1] / "models" / "febrl3_meta.json"
    if meta_p.exists():
        _ML_META = json.loads(meta_p.read_text())
except: pass

def _featurize(a: dict, b: dict):
    name_a = str(a.get("name") or a.get("given_name") or "")
    name_b = str(b.get("name") or b.get("given_name") or "")
    name_sim = fuzz.ratio(name_a, name_b) / 100 if name_a and name_b else 0
    pc_a = str(a.get("postcode") or a.get("metadata",{}).get("postcode") or a.get("address",{}).get("postcode") if isinstance(a.get("address"), dict) else "" or "")
    pc_b = str(b.get("postcode") or b.get("metadata",{}).get("postcode") or b.get("address",{}).get("postcode") if isinstance(b.get("address"), dict) else "" or "")
    pc_exact = 1.0 if pc_a and pc_a == pc_b else 0.0
    ext_a = str(a.get("external_id") or a.get("soc_sec_id") or a.get("phone") or "")
    ext_b = str(b.get("external_id") or b.get("soc_sec_id") or b.get("phone") or "")
    ext_exact = 1.0 if ext_a and ext_a == ext_b else 0.0
    suburb_a = str(a.get("address",{}).get("city") or a.get("metadata",{}).get("suburb") or "" if isinstance(a.get("address"), dict) else a.get("suburb") or "")
    suburb_b = str(b.get("address",{}).get("city") or b.get("metadata",{}).get("suburb") or "" if isinstance(b.get("address"), dict) else b.get("suburb") or "")
    suburb_sim = fuzz.ratio(suburb_a, suburb_b) / 100 if suburb_a and suburb_b else 0
    dob_a = str(a.get("date_of_birth") or "")
    dob_b = str(b.get("date_of_birth") or "")
    dob_exact = 1.0 if dob_a and dob_a == dob_b else 0.0
    token_overlap = len(set(name_a.lower().split()) & set(name_b.lower().split())) / max(1, len(set(name_a.lower().split()) | set(name_b.lower().split())))
    len_diff = abs(len(name_a) - len(name_b)) / max(1, max(len(name_a), len(name_b)))
    return [name_sim, pc_exact, ext_exact, suburb_sim, dob_exact, token_overlap, len_diff]

class MatchingEngine:
    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None, use_ml: bool = True):
        self.use_ml = use_ml and _ML_MODEL is not None
        self.ml_model = _ML_MODEL if self.use_ml else None
        self.rules: List[MatchingRule] = []
        if rules:
            for r in rules:
                self.rules.append(MatchingRule(**r))
        if not self.rules:
            self.rules = [
                MatchingRule(field_name="name", match_type="fuzzy", weight=0.4, threshold=0.85),
                MatchingRule(field_name="email", match_type="exact", weight=0.3),
                MatchingRule(field_name="phone", match_type="exact", weight=0.3),
            ]

    def exact_match(self, val_a: Any, val_b: Any) -> bool:
        if val_a is None or val_b is None:
            return False
        return str(val_a).strip().lower() == str(val_b).strip().lower()

    def prefix_match(self, val_a: Any, val_b: Any) -> bool:
        if val_a is None or val_b is None:
            return False
        a = str(val_a).strip().lower()
        b = str(val_b).strip().lower()
        return a.startswith(b) or b.startswith(a)

    def suffix_match(self, val_a: Any, val_b: Any) -> bool:
        if val_a is None or val_b is None:
            return False
        a = str(val_a).strip().lower()
        b = str(val_b).strip().lower()
        return a.endswith(b) or b.endswith(a)

    def contains_match(self, val_a: Any, val_b: Any) -> bool:
        if val_a is None or val_b is None:
            return False
        a = str(val_a).strip().lower()
        b = str(val_b).strip().lower()
        return a in b or b in a

    def fuzzy_match(self, val_a: Any, val_b: Any, threshold: float = 85.0) -> Tuple[bool, float]:
        if val_a is None or val_b is None:
            return False, 0.0
        score = fuzz.ratio(str(val_a), str(val_b))
        return score >= threshold, score / 100.0

    def compare_field(self, field_name: str, val_a: Any, val_b: Any) -> Tuple[bool, float, str]:
        rule = next((r for r in self.rules if r.field_name == field_name), None)
        if rule is None:
            return self.exact_match(val_a, val_b), 1.0 if str(val_a) == str(val_b) else 0.0, "exact"
        match_type = rule.match_type
        if match_type == "exact":
            matched = self.exact_match(val_a, val_b)
            return matched, (1.0 if matched else 0.0), "exact"
        elif match_type == "prefix":
            matched = self.prefix_match(val_a, val_b)
            return matched, (1.0 if matched else 0.0), "prefix"
        elif match_type == "suffix":
            matched = self.suffix_match(val_a, val_b)
            return matched, (1.0 if matched else 0.0), "suffix"
        elif match_type == "contains":
            matched = self.contains_match(val_a, val_b)
            return matched, (1.0 if matched else 0.0), "contains"
        elif match_type == "fuzzy":
            threshold = rule.threshold if rule.threshold else 85.0
            matched, score = self.fuzzy_match(val_a, val_b, threshold)
            return matched, score, "fuzzy"
        else:
            matched = self.exact_match(val_a, val_b)
            return matched, (1.0 if matched else 0.0), "exact"

    def compute_score(self, record_a: Dict[str, Any], record_b: Dict[str, Any]) -> Tuple[float, List[str], Dict[str, Any]]:
        if self.use_ml and self.ml_model is not None:
            try:
                feats = _featurize(record_a, record_b)
                prob = float(self.ml_model.predict_proba([feats])[0][1])
                # also compute rule evidence for explainability
                matched_fields = []
                evidence = {}
                for rule in self.rules:
                    val_a = record_a.get(rule.field_name)
                    val_b = record_b.get(rule.field_name)
                    if val_a is None and val_b is None:
                        continue
                    if val_a is None or val_b is None:
                        evidence[rule.field_name] = {"match": False, "reason": "missing_field"}
                        continue
                    matched, score, method = self.compare_field(rule.field_name, val_a, val_b)
                    evidence[rule.field_name] = {"match": matched, "score": score, "method": method, "val_a": str(val_a), "val_b": str(val_b)}
                    if matched:
                        matched_fields.append(rule.field_name)
                # add ML fields
                evidence["ml_prob"] = prob
                evidence["ml_features"] = {"name_sim": feats[0], "pc_exact": feats[1], "ext_exact": feats[2], "suburb_sim": feats[3], "dob_exact": feats[4], "token_overlap": feats[5], "len_diff": feats[6]}
                evidence["model"] = "LogisticRegression (trained on FEBRL3 + product datasets)"
                return prob, matched_fields, evidence
            except Exception as e:
                logger.error("ML predict failed, fallback to rule", error=str(e))
        matched_fields = []
        evidence = {}
        total_weight = 0.0
        weighted_score = 0.0
        for rule in self.rules:
            field_name = rule.field_name
            val_a = record_a.get(field_name)
            val_b = record_b.get(field_name)
            if val_a is None and val_b is None:
                continue
            if val_a is None or val_b is None:
                evidence[field_name] = {"match": False, "reason": "missing_field"}
                continue
            matched, score, method = self.compare_field(field_name, val_a, val_b)
            weight = rule.weight
            total_weight += weight
            weighted_score += score * weight
            evidence[field_name] = {"match": matched, "score": score, "method": method, "val_a": str(val_a), "val_b": str(val_b)}
            if matched:
                matched_fields.append(field_name)
        confidence = weighted_score / total_weight if total_weight > 0 else 0.0
        return confidence, matched_fields, evidence

    def find_matches(self, records: List[Dict[str, Any]], threshold: float = 0.6) -> List[MatchResult]:
        results = []
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                record_a = records[i]
                record_b = records[j]
                confidence, matched_fields, evidence = self.compute_score(record_a, record_b)
                if confidence >= threshold:
                    result = MatchResult(
                        record_a_id=record_a.get("id", i),
                        record_b_id=record_b.get("id", j),
                        confidence=round(confidence, 4),
                        match_method="ml" if self.use_ml else ("fuzzy" if confidence < 1.0 else "exact"),
                        matched_fields=matched_fields,
                        evidence=evidence,
                        is_resolved=False,
                    )
                    results.append(result)
        logger.info("Found matches", count=len(results), threshold=threshold, model="ml" if self.use_ml else "rule")
        return results

    def find_entity_groups(self, records: List[Dict[str, Any]], threshold: float = 0.6) -> List[EntityGroup]:
        matches = self.find_matches(records, threshold)
        parent: Dict[int, int] = {}
        def find(x: int) -> int:
            if x not in parent:
                parent[x] = x
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(x: int, y: int):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry
        record_ids = set()
        for match in matches:
            record_ids.add(match.record_a_id)
            record_ids.add(match.record_b_id)
            union(match.record_a_id, match.record_b_id)
        groups_map: Dict[int, List[int]] = {}
        for rid in record_ids:
            root = find(rid)
            if root not in groups_map:
                groups_map[root] = []
            groups_map[root].append(rid)
        entity_groups = []
        for idx, (_, record_ids_list) in enumerate(groups_map.items()):
            if len(record_ids_list) < 2:
                continue
            entity_groups.append(EntityGroup(
                group_id=str(idx),
                record_ids=sorted(record_ids_list),
                confidence=0.0,
                match_method="ml" if self.use_ml else "deterministic",
            ))
        logger.info("Found entity groups", count=len(entity_groups))
        return entity_groups
