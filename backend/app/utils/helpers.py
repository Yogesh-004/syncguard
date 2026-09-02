"""Utility helper functions."""
import json
import hashlib
import uuid
import os
from typing import Any, Dict, Optional, List
from datetime import datetime


def generate_id() -> str:
    return str(uuid.uuid4())


def generate_hash(data: str, salt: str = "") -> str:
    return hashlib.sha256(f"{salt}{data}".encode("utf-8")).hexdigest()


def serialize_datetime(obj: Any) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def sanitize_filename(filename: str) -> str:
    import re
    sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    return sanitized[:255]


def parse_connection_string(conn_str: str) -> Dict[str, str]:
    parts = conn_str.split("://", 1)
    if len(parts) != 2:
        return {"type": "unknown", "raw": conn_str}
    scheme = parts[0]
    rest = parts[1]
    if "@" in rest:
        auth, host_port = rest.split("@", 1)
        user_pass = auth.split(":")
        user = user_pass[0] if len(user_pass) > 0 else ""
        password = user_pass[1] if len(user_pass) > 1 else ""
    else:
        host_port = rest
        user = ""
        password = ""
    if "/" in host_port:
        host_port, db_name = host_port.rsplit("/", 1)
    else:
        db_name = ""
    if ":" in host_port:
        host, port = host_port.split(":")
    else:
        host = host_port
        port = ""
    return {
        "scheme": scheme,
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "database": db_name,
    }


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def retry_on_failure(max_retries: int = 3, delay: int = 1, exceptions: tuple = (Exception,)):
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(delay)
                    else:
                        raise last_exception
        return wrapper
    return decorator


def to_json(obj: Any) -> str:
    return json.dumps(obj, default=serialize_datetime, indent=2)


def from_json(data: str) -> Any:
    return json.loads(data)