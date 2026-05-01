from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RepositoryComplianceCheck:
    name: str
    status: str
    required: bool
    maturity_level: int
    description: str
    link_to_guidance: Optional[str] = None


@dataclass
class RepositoryComplianceReportView:
    name: str
    compliance_status: str
    checks: List[RepositoryComplianceCheck]
    maturity_level: int = 0
    authoritative_business_unit_owners: List[str] = field(default_factory=lambda: [])
    authoritative_team_owners: List[str] = field(default_factory=lambda: [])
    description: Optional[str] = None
