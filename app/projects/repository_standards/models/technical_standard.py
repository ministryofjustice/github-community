from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TechnicalStandardCheck:
    number: int
    name: str
    status: str
    description: str
    link_to_guidance: str
    recommendations: List[str] = field(default_factory=list)


@dataclass
class TechnicalStandardReportView:
    name: str
    compliant: bool
    checks: List[TechnicalStandardCheck]
    authoritative_business_unit_owners: List[str] = field(default_factory=list)
    authoritative_team_owners: List[str] = field(default_factory=list)
    description: Optional[str] = None
    last_updated: datetime | None = None
    visibility: str | None = None
    organisation: str = "ministryofjustice"

    @property
    def checks_passed(self) -> int:
        return sum(check.status == "pass" for check in self.checks)

    @property
    def compliance_percentage(self) -> float:
        return self.checks_passed / len(self.checks) * 100 if self.checks else 0