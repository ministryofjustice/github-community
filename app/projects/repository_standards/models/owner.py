import json
from dataclasses import dataclass
from typing import List, Optional

from app.projects.repository_standards.models.repository_compliance import (
    RepositoryComplianceCheck,
)


@dataclass
class Owner:
    name: str
    teams: List[str]
    prefix: Optional[str] = None
    checks: Optional[List[RepositoryComplianceCheck]] = None


@dataclass
class OwnerConfig:
    name: str
    teams: List[str]
    prefix: Optional[str] = None

    def to_dict(self):
        return json.loads(json.dumps(self, default=lambda o: o.__dict__))

    @classmethod
    def from_dict(cls, data: dict) -> "OwnerConfig":
        return cls(name=data["name"], teams=data["teams"], prefix=data["prefix"])
