from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TechnicalStandardCheck:
    number: int
    name: str
    status: str
    description: str
    link_to_guidance: str


@dataclass
class TechnicalStandardReportView:
    name: str
    compliant: bool
    checks: List[TechnicalStandardCheck]
    authoritative_business_unit_owners: List[str] = field(default_factory=list)
    authoritative_team_owners: List[str] = field(default_factory=list)
    description: Optional[str] = None