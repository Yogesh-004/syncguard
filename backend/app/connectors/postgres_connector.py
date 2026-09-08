"""Controlled PostgreSQL target connector (Phase 6B).

REAL external target: a separate PostgreSQL server/database from SyncGuard's
own application DB (default 127.0.0.1:55432, disposable `syncguard_target`).
Never touches RecordModel/source systems and never calls MockConnector.

Safety properties:
- All SQL parameterized; table/field identifiers come from fixed allow-lists,
  never from user input.
- Writes run in one transaction: version-guarded UPDATE + idempotency-row
  INSERT commit atomically; any failure rolls back (no partial updates).
- Stale destinations are rejected, never overwritten (compare-before-write on
  `version` inside the write transaction).
- Idempotency keys are enforced in the target itself (`applied_operations`
  PK): same key + same mutation replays the original result without
  re-mutating; same key + different mutation raises (never applies).
- DSN/secrets are never logged (only host/db/user/table are).
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.core.logging import logger

LABEL = "POSTGRESQL TARGET"
DEFAULT_TABLE = "customer_records"
DEFAULT_OPS_TABLE = "applied_operations"
ALLOWED_FIELDS = ("name", "email", "phone")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customer_records (
    record_key TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    phone TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS applied_operations (
    idempotency_key TEXT PRIMARY KEY,
    record_key TEXT NOT NULL,
    field_name TEXT NOT NULL,
    resolved_value TEXT,
    version_after INTEGER NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class PostgresConnectorError(Exception):
    """Base error with a machine-readable failure class (no secrets)."""


class RecordMissingError(PostgresConnectorError):
    failure_class = "DESTINATION_MISSING"


class ValidationError(PostgresConnectorError):
    failure_class = "VALIDATION"


class StaleTargetError(PostgresConnectorError):
    failure_class = "STALE_DESTINATION"


class IdempotencyCollisionError(PostgresConnectorError):
    failure_class = "IDEMPOTENCY_COLLISION"


class TransientTargetError(PostgresConnectorError):
    failure_class = "TRANSIENT"


class VerificationMismatchError(PostgresConnectorError):
    failure_class = "VERIFICATION_MISMATCH"


def _redacted_dsn(dsn: str) -> str:
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(dsn)
        host = parts.hostname or "?"
        db = (parts.path or "").lstrip("/") or "?"
        user = parts.username or "?"
        return f"postgresql://{user}@{host}/{db}"
    except Exception:
        return "postgresql://?/?"


class PostgresConnector:
    connector_type = "postgres"

    def __init__(self, dsn: Optional[str] = None, table: str = DEFAULT_TABLE,
                 ops_table: str = DEFAULT_OPS_TABLE, timeout_s: int = 10,
                 options: Optional[str] = None):
        if table != DEFAULT_TABLE or ops_table != DEFAULT_OPS_TABLE:
            raise ValidationError(f"Unknown target table (allow-listed: {DEFAULT_TABLE})")
        self.dsn = dsn or os.environ.get("SYNCGUARD_PG_TARGET", "")
        if not self.dsn:
            raise ValidationError("PostgreSQL target DSN not configured (SYNCGUARD_PG_TARGET)")
        self.table = table
        self.ops_table = ops_table
        self.timeout_s = timeout_s
        self.options = options
        self.destination = f"PG:{DEFAULT_TABLE}"

    def _connect(self):
        import psycopg2
        kwargs: Dict[str, Any] = {"connect_timeout": self.timeout_s}
        if self.options:
            kwargs["options"] = self.options
        return psycopg2.connect(self.dsn, **kwargs)

    def health_check(self) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"destination": self.destination, "label": LABEL, "healthy": True,
                "target": _redacted_dsn(self.dsn)}

    def get_record(self, record_key: Any) -> Optional[Dict[str, Any]]:
        try:
            conn = self._connect()
        except Exception as exc:
            raise TransientTargetError(f"Target unreachable: {type(exc).__name__}") from exc
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT record_key, name, email, phone, version, updated_at FROM {self.table} "
                    "WHERE record_key = %s", (str(record_key),))
                row = cur.fetchone()
        if not row:
            return None
        return {"record_key": row[0], "name": row[1], "email": row[2], "phone": row[3],
                "version": row[4], "updated_at": row[5].isoformat() if row[5] else None}

    def preview(self, record_key: Any, field: str, value: Any, idempotency_key: str) -> Dict[str, Any]:
        """Genuinely non-mutating dry-run: SELECTs only, no transaction writes."""
        if field not in ALLOWED_FIELDS:
            raise ValidationError(f"Field '{field}' is not writable on the controlled target")
        current = self.get_record(record_key)
        if current is None:
            raise RecordMissingError(f"Target record '{record_key}' does not exist")
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError(f"Empty value not allowed for field '{field}'")
        return {"destination": self.destination, "label": LABEL, "record_key": str(record_key),
                "field": field, "current_value": current.get(field),
                "current_version": current["version"], "proposed_value": value,
                "expected_version": current["version"],
                "expected_state": {**{k: current[k] for k in ALLOWED_FIELDS},
                                   field: value, "version": current["version"] + 1},
                "validation": "ok", "stale_warning": None,
                "idempotency_key": idempotency_key, "mutated": False}

    def apply(self, record_key: Any, field: str, value: Any, expected_version: int,
              idempotency_key: str) -> Dict[str, Any]:
        """Transactional guarded write. Raises on stale/missing/invalid/collision."""
        if field not in ALLOWED_FIELDS:
            raise ValidationError(f"Field '{field}' is not writable on the controlled target")
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError(f"Empty value not allowed for field '{field}'")
        if expected_version is None:
            raise ValidationError("expected_version is required (stale-state guard)")
        key = str(record_key)
        try:
            conn = self._connect()
        except Exception as exc:
            raise TransientTargetError(f"Target unreachable: {type(exc).__name__}") from exc
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(f"SELECT record_key, field_name, resolved_value, version_after "
                            f"FROM {self.ops_table} WHERE idempotency_key = %s", (idempotency_key,))
                prior = cur.fetchone()
                if prior is not None:
                    same = (prior[0] == key and prior[1] == field
                            and json.dumps(value, sort_keys=True, default=str)
                            == json.dumps(json.loads(prior[2]), sort_keys=True, default=str))
                    conn.rollback()
                    if same:
                        logger.info("PG idempotent replay", destination=self.destination, record_key=key)
                        return {"destination": self.destination, "label": LABEL, "record_key": key,
                                "field": field, "value": value, "version_after": prior[3],
                                "applied": False, "duplicate": True,
                                "operation_id": idempotency_key}
                    raise IdempotencyCollisionError(
                        f"Idempotency key '{idempotency_key}' already used for a different mutation")
                cur.execute(f"SELECT version FROM {self.table} WHERE record_key = %s FOR UPDATE", (key,))
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    raise RecordMissingError(f"Target record '{key}' does not exist")
                if int(row[0]) != int(expected_version):
                    conn.rollback()
                    raise StaleTargetError(
                        f"Target version {row[0]} != expected {expected_version} — refusing overwrite")
                cur.execute(f"UPDATE {self.table} SET {field} = %s, version = version + 1, "
                            f"updated_at = now() WHERE record_key = %s", (str(value), key))
                cur.execute(f"INSERT INTO {self.ops_table} "
                            f"(idempotency_key, record_key, field_name, resolved_value, version_after) "
                            f"VALUES (%s, %s, %s, %s, %s)",
                            (idempotency_key, key, field,
                             json.dumps(value, default=str), int(expected_version) + 1))
            conn.commit()
        except PostgresConnectorError:
            raise
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            raise self._classify(exc) from exc
        finally:
            try:
                conn.close()
            except Exception:
                pass
        logger.info("PG target updated", destination=self.destination, record_key=key, field=field)
        return {"destination": self.destination, "label": LABEL, "record_key": key,
                "field": field, "value": value, "version_after": int(expected_version) + 1,
                "applied": True, "duplicate": False, "operation_id": idempotency_key}

    def confirm(self, record_key: Any, field: str, value: Any, version_after: int,
                idempotency_key: str) -> Dict[str, Any]:
        """Verify-before-retry: safe read to decide whether a transient failure
        already applied the mutation. Never mutates."""
        current = self.get_record(record_key)
        if (current is not None and str(current.get(field)) == str(value)
                and int(current["version"]) == int(version_after)):
            return {"applied": True, "verified": True, "version_after": int(version_after),
                    "operation_id": idempotency_key}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT record_key, field_name, resolved_value, version_after "
                            f"FROM {self.ops_table} WHERE idempotency_key = %s", (idempotency_key,))
                prior = cur.fetchone()
        if prior is not None:
            return {"applied": True, "verified": False, "note": "operation recorded, state diverged",
                    "operation_id": idempotency_key}
        return {"applied": False, "verified": False, "operation_id": idempotency_key}

    def verify(self, record_key: Any, field: str, expected_value: Any,
               expected_version: int) -> Dict[str, Any]:
        """Fresh read + compare. SQL success alone is never reported as success."""
        current = self.get_record(record_key)
        if current is None:
            return {"verified": False, "reason": "record missing on read-back", "actual": None}
        ok = (str(current.get(field)) == str(expected_value)
              and int(current["version"]) == int(expected_version))
        return {"verified": ok, "actual": {k: current[k] for k in ALLOWED_FIELDS + ("version",)},
                "reason": None if ok else "post-write state != expected approved state"}

    def _classify(self, exc: Exception) -> PostgresConnectorError:
        msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        transient_markers = ("timeout", "timed out", "connection", "operationalerror",
                             "lock timeout", "could not connect", "server closed")
        if any(t in msg.lower() for t in transient_markers):
            return TransientTargetError(msg)
        return PostgresConnectorError(msg)

    def log_context(self) -> Dict[str, Any]:
        return {"destination": self.destination, "label": LABEL,
                "target": _redacted_dsn(self.dsn), "table": self.table}
