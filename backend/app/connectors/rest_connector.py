"""REST connector for data ingestion."""
from typing import Any, Dict, List, Optional, Iterator
import json
from urllib.request import urlopen, Request
from urllib.error import URLError
from backend.app.core.logging import logger


class RESTConnector:
    def __init__(self, connection_string: Optional[str] = None, timeout: int = 30):
        self.connection_string = connection_string
        self.timeout = timeout
        self.connector_type = "rest"
        self.headers = {"Accept": "application/json"}

    def set_header(self, key: str, value: str) -> None:
        self.headers[key] = value

    def _request(self, url: str, method: str = "GET", body: Optional[Dict[str, Any]] = None) -> Any:
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, method=method, headers=self.headers)
        try:
            with urlopen(req, timeout=self.timeout) as response:
                content = response.read().decode("utf-8")
                return json.loads(content) if content else None
        except URLError as e:
            logger.error("REST request failed", url=url, error=str(e))
            raise

    def read(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        url = endpoint
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{endpoint}?{query}"
        data = self._request(url)
        if data is None:
            return
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
                else:
                    yield {"value": item}
        elif isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            yield {"_key": key, **item}
                        else:
                            yield {"_key": key, "value": item}
                elif isinstance(value, dict):
                    yield {"_key": key, **value}
                else:
                    yield {"_key": key, "value": value}
        logger.info("REST read complete", endpoint=endpoint)

    def read_all(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        records = list(self.read(endpoint, params=params))
        logger.info("REST records loaded", count=len(records), endpoint=endpoint)
        return records

    def post(self, endpoint: str, body: Dict[str, Any]) -> Any:
        result = self._request(endpoint, method="POST", body=body)
        logger.info("REST POST complete", endpoint=endpoint)
        return result

    def put(self, endpoint: str, body: Dict[str, Any]) -> Any:
        result = self._request(endpoint, method="PUT", body=body)
        logger.info("REST PUT complete", endpoint=endpoint)
        return result

    def delete(self, endpoint: str) -> Any:
        result = self._request(endpoint, method="DELETE")
        logger.info("REST DELETE complete", endpoint=endpoint)
        return result

    def validate(self, endpoint: str, required_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        records = self.read_all(endpoint)
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