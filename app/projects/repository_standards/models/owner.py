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
