"""Mock destination connector for Phase 3 — clearly labelled MOCK everywhere.

Never touches RecordModel/source systems. Writes go to an isolated in-memory
store keyed by (destination, record_id, field) so verification can read back.
Failure injection is ONLY possible via explicit `simulate_error` on the mock
destination (used by failure e2e tests), never against real systems.
"""
from typing import Any, Dict, Optional

from backend.app.core.logging import logger

LABEL = "MOCK DESTINATION"

_store: Dict[str, Any] = {}


def _key(destination: str, record_id: Any, field: str) -> str:
    return f"{destination}|{record_id}|{field}"


class MockConnector:
    connector_type = "mock"

    def __init__(self, destination: str = "MOCK CRM"):
        self.destination = destination if destination.upper().startswith("MOCK") else f"MOCK {destination}"

    def health_check(self) -> Dict[str, Any]:
        return {"destination": self.destination, "label": LABEL, "healthy": True}

    def get_record(self, record_id: Any, field: Optional[str] = None) -> Dict[str, Any]:
        if field:
            return {"destination": self.destination, "record_id": record_id, "field": field, "value": _store.get(_key(self.destination, record_id, field))}
        return {"destination": self.destination, "record_id": record_id, "values": {k.split("|", 2)[2]: v for k, v in _store.items() if k.startswith(f"{self.destination}|{record_id}|")}}

    def update_record(self, record_id: Any, field: str, value: Any, simulate_error: Optional[Any] = None) -> Dict[str, Any]:
        if simulate_error in (429, 500, 502, 503, 408):
            logger.error("Mock connector simulated retryable failure", status=simulate_error)
            raise ConnectionError(f"MOCK {simulate_error}: simulated transient failure")
        if simulate_error == "timeout":
            logger.error("Mock connector simulated timeout")
            raise TimeoutError("MOCK timeout: simulated read timeout")
        if simulate_error == "timeout_before":
            logger.error("Mock connector simulated pre-write timeout (no mutation)")
            raise TimeoutError("MOCK timeout_before: timed out before mutation reached target")
        if simulate_error == "connection":
            logger.error("Mock connector simulated connection failure")
            raise ConnectionError("MOCK connection: simulated connection refused")
        if simulate_error == "post_commit_loss":
            _store[_key(self.destination, record_id, field)] = value
            logger.error("Mock connector simulated post-commit response loss (mutation applied, reply lost)")
            raise ConnectionError("MOCK post_commit_loss: commit applied, response lost — outcome UNKNOWN")
        if simulate_error in (400, 401, 403, 404, 409, 422):
            logger.error("Mock connector simulated non-retryable failure", status=simulate_error)
            raise ValueError(f"MOCK {simulate_error}: simulated permanent failure")
        _store[_key(self.destination, record_id, field)] = value
        logger.info("Mock destination updated", destination=self.destination, record_id=record_id, field=field)
        return {"destination": self.destination, "label": LABEL, "record_id": record_id, "field": field, "value": value, "mock": True}

    @classmethod
    def clear(cls) -> None:
        _store.clear()
