"""JSON connector for data ingestion."""
from typing import Any, Dict, List, Optional, Iterator
import json
import os
from backend.app.core.logging import logger


class JSONConnector:
    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string
        self.connector_type = "json"

    def read(self, source: str) -> Iterator[Dict[str, Any]]:
        if source.startswith("http://") or source.startswith("https://"):
            import urllib.request
            with urllib.request.urlopen(source) as response:
                content = response.read().decode("utf-8")
            data = json.loads(content)
        else:
            with open(source, "r", encoding="utf-8") as f:
                data = json.load(f)

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    yield {"_key": key, **value}
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            yield {"_key": key, **item}
                        else:
                            yield {"_key": key, "value": item}
                else:
                    yield {"_key": key, "value": value}
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
                else:
                    yield {"value": item}
        logger.info("JSON read complete", source=source)

    def read_all(self, source: str) -> List[Dict[str, Any]]:
        records = list(self.read(source))
        logger.info("JSON records loaded", count=len(records), source=source)
        return records

    def write(self, records: List[Dict[str, Any]], filename: str) -> str:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, default=str)
        logger.info("JSON written", filename=filename, count=len(records))
        return filename

    def validate(self, source: str, required_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        records = self.read_all(source)
        validation = {
            "valid": True,
            "record_count": len(records),
            "errors": [],
        }
        if not records:
            validation["valid"] = False
            validation["errors"].append("No records found")
            return validation
        if required_fields:
            for i, record in enumerate(records):
                for field in required_fields:
                    if field not in record:
                        validation["valid"] = False
                        validation["errors"].append(f"Record {i} missing field: {field}")
        return validation