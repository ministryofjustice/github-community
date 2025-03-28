from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RepositoryComplianceCheck:
    name: str
    status: str
    required: bool
    description: str
    link_to_guidance: Optional[str] = None


@dataclass
class RepositoryComplianceReportView:
    name: str
    compliance_status: str
    checks: List[RepositoryComplianceCheck]
    authorative_owner: Optional[str] = None
    description: Optional[str] = None
