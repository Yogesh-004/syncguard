"""Phase 4.5 edge cases — decision engine behavior (25 cases + critical regression)."""
from backend.app.services import decision_engine as de

A = {"name": "Rahul Kumar", "email": "rahul@gmail.com", "phone": "+919876543210",
     "address": {"street": "1 MG Road", "city": "Bangalore", "postcode": "560001"},
     "postcode": "560001", "external_id": "CUST-1024", "date_of_birth": "1990-01-01", "amount": 5000}


def v(over_a=None, over_b=None, score=0.95):
    a, b = dict(A), dict(A)
    a.update(over_a or {})
    b.update(over_b or {})
    return de.decide_pair(a, b, score)


def test_01_exact_everything():
    r = v()
    assert r["decision"] == "MATCH" and r["auto_resolvable"] is True and r["risk"] == "LOW"


def test_02_email_case_whitespace():
    r = v({"email": " Rahul@Gmail.com "}, {})
    assert r["decision"] == "MATCH"


def test_03_name_diff_email_same():
    r = v({"name": "Rahul Kumar"}, {"name": "Rahul K"}, score=0.9)
    assert r["decision"] in ("MATCH", "POSSIBLE_MATCH")


def test_04_phone_same_email_diff():
    r = v({}, {"email": "other@gmail.com"}, score=0.9)
    assert r["decision"] != "MATCH" or r["risk"] in ("HIGH", "CRITICAL")
    assert r["auto_resolvable"] is False


def test_05_same_postcode_diff_person():
    r = de.decide_pair({"name": "Asha Rao", "postcode": "560001"}, {"name": "Vikram Nair", "postcode": "560001"}, 0.65)
    assert r["decision"] != "MATCH" or r["auto_resolvable"] is False


def test_06_same_name_city_diff_contact():
    r = de.decide_pair({"name": "John Smith", "email": "a@x.com", "phone": "111"},
                       {"name": "John Smith", "email": "b@y.com", "phone": "222"}, 0.8)
    assert r["auto_resolvable"] is False and r["risk"] == "HIGH"


def test_07_missing_email():
    r = v({"email": None}, {})
    assert r["auto_resolvable"] is False


def test_08_missing_phone():
    r = v({"phone": None}, {})
    assert r["auto_resolvable"] is False


def test_09_missing_name():
    r = v({"name": None}, {}, score=0.8)
    assert r["auto_resolvable"] is False


def test_10_all_identifiers_missing():
    r = de.decide_pair({"name": "X", "address": {"city": "Y"}}, {"name": "X", "address": {"city": "Y"}}, 0.7)
    assert r["auto_resolvable"] is False
    assert r["recommendation"] in ("MANUAL REVIEW", "DO NOT MERGE")
    assert r["risk"] in ("MEDIUM", "HIGH")


def test_11_conflicting_ids():
    r = v({"external_id": "CUST-1024"}, {"external_id": "CUST-8831"}, score=0.95)
    assert r["decision"] == "NO_MATCH" and r["risk"] == "CRITICAL" and r["auto_resolvable"] is False


def test_12_conflicting_emails():
    r = v({}, {"email": "x@y.com"}, score=0.95)
    assert r["auto_resolvable"] is False and r["risk"] in ("HIGH", "CRITICAL")


def test_13_conflicting_phones():
    r = v({}, {"phone": "+919876500000"}, score=0.95)
    assert r["auto_resolvable"] is False


def test_14_unicode_names():
    r = de.decide_pair({"name": "José García", "email": "a@x.com"}, {"name": "Jose Garcia", "email": "a@x.com"}, 0.9)
    assert r["decision"] in ("MATCH", "POSSIBLE_MATCH")


def test_15_reordered_names():
    r = de.decide_pair({"name": "John A Smith", "email": "a@x.com"}, {"name": "Smith, John A", "email": "a@x.com"}, 0.85)
    assert r["decision"] in ("MATCH", "POSSIBLE_MATCH")


def test_16_spelling():
    r = de.decide_pair({"name": "John Smith", "email": "a@x.com"}, {"name": "Jon Smythe", "email": "a@x.com"}, 0.8)
    assert not (r["decision"] == "MATCH" and r["final_confidence"] == 1.0)


def test_17_duplicates_identical():
    r = v()
    assert r["final_confidence"] < 1.0


def test_18_unrelated():
    r = de.decide_pair({"name": "Asha Rao", "email": "a@x.com", "phone": "111"},
                       {"name": "Bob Ray", "email": "b@y.com", "phone": "222"}, 0.2)
    assert r["decision"] == "NO_MATCH" and r["recommendation"] == "DO NOT MERGE"


def test_19_one_field_only():
    r = de.decide_pair({"name": "Asha Rao"}, {"name": "Asha Rao"}, 0.6)
    assert r["auto_resolvable"] is False


def test_20_identical_records_capped():
    r = v(score=1.0)
    assert r["final_confidence"] <= 0.99


def test_21_near_identical_critical_conflict():
    r = v({}, {"email": "other@gmail.com", "phone": "+910000000000"}, score=0.99)
    assert r["decision"] != "MATCH" or r["auto_resolvable"] is False
    assert r["risk"] in ("HIGH", "CRITICAL")


def test_22_noisy_address():
    r = v({"address": {"street": "1, M.G. Road!!", "city": "bangalore "}}, {"address": {"street": "1 MG Road", "city": "Bangalore"}}, score=0.9)
    assert r["decision"] in ("MATCH", "POSSIBLE_MATCH")


def test_23_malformed_input_no_crash():
    r = de.decide_pair({"name": 123, "email": ["x"], "phone": {}}, {"name": None}, 0.5)
    assert r["decision"] in ("MATCH", "POSSIBLE_MATCH", "NO_MATCH")


def test_24_scientific_numeric():
    r = v({"amount": "1e6"}, {"amount": 1000000.0}, score=0.9)
    assert r["decision"] in ("MATCH", "POSSIBLE_MATCH")


def test_25_nulls():
    r = de.decide_pair({"name": None, "email": None}, {"name": None, "email": None}, 0.9)
    assert r["auto_resolvable"] is False


def test_critical_regression_no_false_verified():
    r = de.decide_pair({"name": "Asha Rao", "postcode": "560001", "address": {"city": "Bangalore", "postcode": "560001"}},
                       {"name": "Asha Rani", "postcode": "560001", "address": {"city": "Bangalore", "postcode": "560001"}}, 0.97)
    assert not (r["decision"] == "MATCH" and r["final_confidence"] == 1.0 and r["auto_resolvable"])
    assert r["verification_status"] == "NEEDS_REVIEW"
    r2 = de.decide_pair({"name": "John Smith", "postcode": "2000", "email": "a@x.com", "phone": "111"},
                        {"name": "John Smyth", "postcode": "2000", "email": "b@y.com", "phone": "222"}, 0.93)
    assert r2["auto_resolvable"] is False and r2["risk"] == "HIGH"
