"""Matching and entity resolution service — ML inference via ModelService (Phase 1)."""
from typing import Any, Dict, List, Optional, Tuple
from rapidfuzz import fuzz
from backend.app.core.logging import logger
from backend.app.schemas.matching import MatchResult, MatchingRule, EntityGroup
from backend.app.services import model_service as _ms


class MatchingEngine:
    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None, use_ml: bool = True, strict_ml: bool = False):
        self.strict_ml = strict_ml
        self.use_ml = use_ml
        self.ml_model = None
        if use_ml:
            try:
                self.ml_model = _ms.load_model()
            except Exception as e:
                if strict_ml:
                    raise
                logger.error("ML model unavailable, rule fallback", error=str(e))
                self.use_ml = False
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
                from backend.app.core.config import settings as _settings
                from backend.app.services import decision_engine as _de
                feats = _ms.featurize(record_a, record_b)
                prob = float(self.ml_model.predict_proba([feats])[0][1])
                verdict = _de.decide_pair(record_a, record_b, prob, _settings.MATCH_THRESHOLD, _settings.POSSIBLE_MATCH_THRESHOLD)
                # rule ticks kept for UI explainability (do NOT drive the decision)
                matched_fields = []
                evidence: Dict[str, Any] = {}
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
                evidence.update({
                    "decision": verdict["decision"],
                    "model_score": verdict["model_score"],
                    "match_score": verdict["model_score"],
                    "ml_prob": verdict["model_score"],
                    "model_version": _ms.get_model_version(),
                    "field_scores": verdict["field_scores"],
                    "field_evidence": verdict["field_evidence"],
                    "penalties": verdict["penalties"],
                    "risk": verdict["risk"],
                    "risk_reason": verdict["risk_reason"],
                    "auto_resolvable": verdict["auto_resolvable"],
                    "recommendation": verdict["recommendation"],
                    "verification_status": verdict["verification_status"],
                    "ml_features": {"name_sim": feats[0], "pc_exact": feats[1], "ext_exact": feats[2], "suburb_sim": feats[3], "dob_exact": feats[4], "token_overlap": feats[5], "len_diff": feats[6]},
                    "model": "LogisticRegression (trained on FEBRL3 + product datasets)",
                })
                return verdict["final_confidence"], matched_fields, evidence
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

    def _build_result(self, record_a: Dict[str, Any], record_b: Dict[str, Any], i: int, j: int,
                      confidence: float, matched_fields: List[str], evidence: Dict[str, Any]) -> MatchResult:
        return MatchResult(
            record_a_id=record_a.get("id", i),
            record_b_id=record_b.get("id", j),
            confidence=round(confidence, 4),
            match_method="ml" if self.use_ml else ("fuzzy" if confidence < 1.0 else "exact"),
            matched_fields=matched_fields,
            evidence=evidence,
            is_resolved=False,
        )

    def find_matches(self, records: List[Dict[str, Any]], threshold: Optional[float] = None) -> List[MatchResult]:
        if threshold is None:
            from backend.app.core.config import settings as _settings
            threshold = _settings.POSSIBLE_MATCH_THRESHOLD
        results = []
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                record_a = records[i]
                record_b = records[j]
                confidence, matched_fields, evidence = self.compute_score(record_a, record_b)
                if confidence >= threshold:
                    results.append(self._build_result(record_a, record_b, i, j, confidence, matched_fields, evidence))
        logger.info("Found matches", count=len(results), threshold=threshold, model="ml" if self.use_ml else "rule")
        return results

    def evaluate_pairs(self, records: List[Dict[str, Any]], nomatch_sample: int = 0,
                         candidates: Optional[set] = None,
                         provenance: Optional[Dict[tuple, List[str]]] = None) -> Dict[str, Any]:
        """Evaluate candidate pairs, returning kept matches + nearest-miss NO_MATCH sample.

        `candidates` is a set of (i, j) index pairs (from blocking); None means
        exhaustive all-pairs (only safe for small inputs — caller decides).
        `provenance` maps pair -> blocking passes that produced it; attached to
        evidence as blocking_reasons (candidate provenance, NOT match evidence).
        NO_MATCH pairs below the possible threshold are normally discarded; the top
        `nomatch_sample` by score are returned labeled NO_MATCH (sampled:true) so the
        review queue can display the tier without persisting millions of rows."""
        from backend.app.core.config import settings as _settings
        if candidates is None:
            n = len(records)
            candidates = {(i, j) for i in range(n) for j in range(i + 1, n)}
        provenance = provenance or {}
        kept: List[MatchResult] = []
        misses: List[tuple] = []
        evaluated = 0
        for i, j in sorted(candidates):
            evaluated += 1
            record_a, record_b = records[i], records[j]
            confidence, matched_fields, evidence = self.compute_score(record_a, record_b)
            evidence["blocking_reasons"] = provenance.get((i, j), ["exhaustive"])
            if confidence >= _settings.POSSIBLE_MATCH_THRESHOLD:
                kept.append(self._build_result(record_a, record_b, i, j, confidence, matched_fields, evidence))
            elif nomatch_sample > 0:
                misses.append((confidence, i, j, matched_fields, evidence))
        misses.sort(key=lambda t: t[0], reverse=True)
        sample = []
        for confidence, i, j, matched_fields, evidence in misses[:nomatch_sample]:
            ev = dict(evidence or {})
            ev["sampled"] = True
            sample.append(self._build_result(records[i], records[j], i, j, confidence, matched_fields, ev))
        logger.info("Pairs evaluated", evaluated=evaluated, kept=len(kept), nomatch_sample=len(sample))
        return {"evaluated_pairs": evaluated, "kept": kept, "nomatch_sample": sample}

    def find_entity_groups(self, records: List[Dict[str, Any]], threshold: Optional[float] = None) -> List[EntityGroup]:
        if threshold is None:
            from backend.app.core.config import settings as _settings
            threshold = _settings.MATCH_THRESHOLD
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
