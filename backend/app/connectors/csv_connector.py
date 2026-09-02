"""CSV connector for data ingestion."""
from typing import Any, Dict, List, Optional, Iterator
import csv
import io
from backend.app.core.logging import logger


class CSVConnector:
    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string
        self.connector_type = "csv"

    def read(self, source: str, encoding: str = "utf-8", delimiter: str = ",") -> Iterator[Dict[str, Any]]:
        if source.startswith("http://") or source.startswith("https://"):
            import urllib.request
            with urllib.request.urlopen(source) as response:
                content = response.read().decode(encoding)
        else:
            with open(source, "r", encoding=encoding) as f:
                content = f.read()
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        for row in reader:
            yield row
        logger.info("CSV read complete", source=source)

    def read_all(self, source: str, encoding: str = "utf-8", delimiter: str = ",") -> List[Dict[str, Any]]:
        records = list(self.read(source, encoding=encoding, delimiter=delimiter))
        logger.info("CSV records loaded", count=len(records), source=source)
        return records

    def write(self, records: List[Dict[str, Any]], filename: str, delimiter: str = ",") -> str:
        if not records:
            return filename
        fieldnames = list(records[0].keys())
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(records)
        with open(filename, "w", encoding="utf-8", newline="") as f:
            f.write(output.getvalue())
        logger.info("CSV written", filename=filename, count=len(records))
        return filename

    def validate(self, source: str, required_fields: Optional[List[str]] = None, encoding: str = "utf-8",
                 delimiter: str = ",") -> Dict[str, Any]:
        records = self.read_all(source, encoding=encoding, delimiter=delimiter)
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
            first = records[0] if records else {}
            for field in required_fields:
                if field not in first:
                    validation["valid"] = False
                    validation["errors"].append(f"Missing required field: {field}")
        return validation