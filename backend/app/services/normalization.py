"""Deterministic data normalization service."""
import re
import hashlib
from datetime import datetime
from typing import Any, Dict, Optional
from backend.app.core.logging import logger


def normalize_name(value: str) -> str:
    if not value or not str(value).strip():
        return ""
    normalized = str(value).strip().upper()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def normalize_phone(value: str) -> str:
    if not value:
        return ""
    raw = str(value).strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if len(digits) > 11:
        return f"+{digits.lstrip('0')}"
    return digits


def normalize_email(value: str) -> str:
    if not value:
        return ""
    return str(value).strip().lower()


def normalize_date(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y.%m.%d", "%d-%m-%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    cleaned = re.sub(r"[^0-9]", "", s)
    if len(cleaned) == 8:
        try:
            if s.count("-") == 2 or s.count("/") == 2:
                for fmt2 in ("%Y%m%d", "%d%m%Y", "%m%d%Y"):
                    try:
                        return datetime.strptime(cleaned, fmt2).strftime("%Y-%m-%d")
                    except ValueError:
                        continue
            return f"{cleaned[0:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
        except Exception:
            pass
    return s


def normalize_address(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if v is None:
                continue
            sk = str(k).strip().lower()
            if sk in ("street", "line1", "address"):
                out["street"] = re.sub(r"\s+", " ", str(v).strip().upper())
            elif sk == "city":
                out["city"] = re.sub(r"\s+", " ", str(v).strip().title())
            elif sk == "state":
                out["state"] = str(v).strip().upper()[:2] if len(str(v).strip()) <= 3 else str(v).strip().title()
            elif sk in ("zip", "zipcode", "postal", "pincode"):
                out["zip"] = re.sub(r"\D", "", str(v))
            elif sk == "country":
                out["country"] = str(v).strip().upper()
            else:
                out[sk] = re.sub(r"\s+", " ", str(v).strip())
        return out
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value.strip().title())
    return value


def normalize_identifier(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def normalize_numeric(value: Any, decimal_places: int = 2) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round(float(value), decimal_places)
    s = str(value).strip()
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in (".", "-", "-."):
        return None
    try:
        return round(float(s), decimal_places)
    except (ValueError, TypeError):
        return None


def normalize_record(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    if "name" in data and data["name"] is not None:
        normalized["name"] = normalize_name(str(data["name"]))
    if "phone" in data and data["phone"] is not None:
        normalized["phone"] = normalize_phone(str(data["phone"]))
    if "email" in data and data["email"] is not None:
        normalized["email"] = normalize_email(str(data["email"]))
    if "date" in data and data["date"] is not None:
        normalized["date"] = normalize_date(data["date"])
    if "address" in data and data["address"] is not None:
        normalized["address"] = normalize_address(data["address"])
    if "identifier" in data and data["identifier"] is not None:
        normalized["identifier"] = normalize_identifier(str(data["identifier"]))
    for key in ("amount", "transaction_amount", "value", "total"):
        if key in data and data[key] is not None:
            normalized[key] = normalize_numeric(data[key])
            break
    for key, val in data.items():
        if key not in normalized:
            if isinstance(val, str):
                normalized[key] = re.sub(r"\s+", " ", val.strip())
            else:
                normalized[key] = val
    logger.info("Record normalized", extra={"keys": list(normalized.keys())})
    return normalized


def deterministic_hash(value: str, salt: str = "") -> str:
    combined = f"{salt}{value}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


def normalize_for_matching(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            cleaned = value.strip().lower()
            cleaned = re.sub(r"[^a-z0-9]", "", cleaned)
            out[key] = cleaned
        elif isinstance(value, (int, float)):
            out[key] = value
        else:
            out[key] = str(value).strip().lower() if value else ""
    return out
