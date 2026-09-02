"""Unit tests for normalization service."""
import pytest
from backend.app.services.normalization import normalize_name, normalize_email, normalize_phone, normalize_date


class TestNormalizeName:
    def test_basic(self):
        assert normalize_name("john doe") == "JOHN DOE"

    def test_whitespace(self):
        assert normalize_name("  john   doe  ") == "JOHN DOE"

    def test_empty(self):
        assert normalize_name("") == ""


class TestNormalizeEmail:
    def test_basic(self):
        assert normalize_email("John@Example.com") == "john@example.com"

    def test_empty(self):
        assert normalize_email("") == ""


class TestNormalizePhone:
    def test_ten_digit(self):
        assert normalize_phone("5551234567") == "+15551234567"

    def test_empty(self):
        assert normalize_phone("") == ""


class TestNormalizeDate:
    def test_yyyymmdd(self):
        assert normalize_date("2024-01-15") is not None

    def test_none(self):
        assert normalize_date(None) is None