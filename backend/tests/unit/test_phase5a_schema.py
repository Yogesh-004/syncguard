"""Phase 5A — schema inference datetime defect (fix scope ONLY)."""
from backend.app.services import schema_analyzer as sa


def test_repro_douglas_abbott_is_string():
    assert sa.infer_schema([{"name": "DOUGLAS ABBOTT"}, {"name": "LARA SMITH"}])[0]["data_type"] == "string"


def test_positive_iso():
    assert sa.infer_type(["2026-01-15", "2025-12-01"]) == "datetime"


def test_positive_dmy():
    assert sa.infer_type(["15/01/2026", "01/12/2025"]) == "datetime"


def test_positive_timestamp():
    assert sa.infer_type(["2026-01-15 14:30:00", "2025-12-01 09:00:00"]) == "datetime"


def test_positive_iso_tz():
    assert sa.infer_type(["2026-01-15T14:30:00+00:00"]) == "datetime"


def test_negative_names():
    assert sa.infer_type(["DOUGLAS ABBOTT", "JOHN SMITH"]) == "string"


def test_negative_company_city_street():
    assert sa.infer_type(["ABC COMPANY", "Acme Inc"]) == "string"
    assert sa.infer_type(["NEW YORK", "Boston"]) == "string"
    assert sa.infer_type(["123 MAIN STREET", "45 Oak Ave"]) == "string"


def test_mixed_empty_null_ws_unicode():
    assert sa.infer_type(["", None, "   ", "José García", "Anne Müller"]) == "string"


def test_mostly_dates_with_missing():
    assert sa.infer_type(["2026-01-15", None, "", "2025-12-01", "2024-06-30"]) == "datetime"


def test_mostly_text_one_date():
    assert sa.infer_type(["DOUGLAS ABBOTT", "LARA SMITH", "2026-01-15"]) == "string"


def test_ambiguous_date_documented():
    # month-first per existing normalize_date order; must not crash, must be datetime
    assert sa.infer_type(["01/02/2026", "03/04/2026"]) == "datetime"


def test_numeric_identifiers_stay_numeric():
    assert sa.infer_type(["000000002941", "000000002289"]) == "integer"
    assert sa.infer_type(["27  SKEETER LN", "x"]) == "string"
