"""Unit tests for matching service."""
import pytest
from backend.app.services.matching import MatchingEngine


class TestMatchingEngine:
    def test_exact_match(self):
        engine = MatchingEngine()
        result = engine.exact_match("John", "John")
        assert result is True

    def test_exact_mismatch(self):
        engine = MatchingEngine()
        result = engine.exact_match("John", "Jane")
        assert result is False

    def test_compute_score(self):
        engine = MatchingEngine()
        record_a = {"name": "John Doe", "email": "john@example.com", "phone": "5551234567"}
        record_b = {"name": "John Doe", "email": "john@example.com", "phone": "5551234567"}
        confidence, matched_fields, evidence = engine.compute_score(record_a, record_b)
        assert confidence == 1.0
        assert len(matched_fields) == 3

    def test_fuzzy_match(self):
        engine = MatchingEngine()
        matched, score = engine.fuzzy_match("John Doe", "Jon Doe")
        assert isinstance(matched, bool)
        assert isinstance(score, float)

    def test_find_matches_empty(self):
        engine = MatchingEngine()
        results = engine.find_matches([], threshold=0.7)
        assert results == []

    def test_find_entity_groups_empty(self):
        engine = MatchingEngine()
        groups = engine.find_entity_groups([], threshold=0.7)
        assert groups == []