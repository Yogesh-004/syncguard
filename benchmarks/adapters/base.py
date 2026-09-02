"""Canonical entity model — extensible."""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class CanonicalRecord:
    entity_id: str
    source: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[Dict[str, Any]] = None
    date_of_birth: Optional[str] = None
    external_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.entity_id,
            "entity_id": self.entity_id,
            "source": self.source,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "date_of_birth": self.date_of_birth,
            "external_id": self.external_id,
            "metadata": self.metadata,
        }

    def to_syncguard_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"id": self.entity_id, "entity_id": self.entity_id}
        if self.name: d["name"] = self.name
        if self.email: d["email"] = self.email
        if self.phone: d["phone"] = self.phone
        if self.address: d["address"] = self.address
        if self.date_of_birth: d["date_of_birth"] = self.date_of_birth
        if self.external_id: d["external_id"] = self.external_id
        for k,v in self.metadata.items():
            if k not in d:
                d[k]=v
        return d
