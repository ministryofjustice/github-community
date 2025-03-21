from typing import List
from urllib.parse import quote

from flask import g

from app.projects.repository_standards.config.repository_compliance_config import (
    get_all_compliance_checks,
)
from app.projects.repository_standards.models.repository_compliance import (
    RepositoryComplianceReportView,
)
from app.projects.repository_standards.repositories.asset_repository import (
    RepositoryView,
)
from app.projects.repository_standards.services.asset_service import (
    AssetService,
    get_asset_service,
)


class RepositoryComplianceService:
    def __init__(self, asset_service: AssetService):
        self.__asset_service = asset_service

    def get_repository_compliance_report(
        self,
        repository: RepositoryView,
    ) -> RepositoryComplianceReportView:
        authorative_owners = [
            owner
            for owner in repository.owner_names
            if self.__asset_service.is_owner_authoritative_for_repository(
                repository, owner
            )
        ]
        authorative_owner = (
            authorative_owners[0] if len(authorative_owners) > 0 else None
        )

        checks = get_all_compliance_checks(repository, authorative_owner)

        compliance_status = (
            "pass"
            if all(not check.required or check.status == "pass" for check in checks)
            else "fail"
        )

        return RepositoryComplianceReportView(
            name=repository.name,
            compliance_status=compliance_status,
            authorative_owner=authorative_owner,
            checks=checks,
            description=repository.data.basic.description,
        )

    def get_all_repositories(self) -> List[RepositoryComplianceReportView]:
        repositories_compliance_reports = []
        repositories = self.__asset_service.get_all_repositories()
        for repository in repositories:
            repository_compliance_report = self.get_repository_compliance_report(
                repository
            )
            repositories_compliance_reports.append(repository_compliance_report)
        return repositories_compliance_reports

    def get_repository_by_name(
        self, repository_name: str
    ) -> RepositoryComplianceReportView | None:
        repository = self.__asset_service.get_repository_by_name(repository_name)
        if not repository:
            return None

        repository_compliance_report = self.get_repository_compliance_report(repository)

        return repository_compliance_report

    def get_repository_complaince_badge_shield_url_by_name(
        self, repository_name: str
    ) -> str:
        repository = self.get_repository_by_name(repository_name)
        logo = "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"
        label = "MoJ Compliant"

        if repository and repository.compliance_status == "pass":
            color = "005ea5"  # MoJ blue
            message = repository.compliance_status.capitalize()
        elif repository and repository.compliance_status == "fail":
            color = "cc0000"  # Red
            message = repository.compliance_status.capitalize()
        else:
            color = "808080"  # Grey
            message = "Not Found"

        return f"https://img.shields.io/badge/{quote(label)}-{quote(message)}-{color}?style=for-the-badge&labelColor=231f20&logo=data:image/png;base64,{quote(logo)}"


def get_repository_compliance_service() -> RepositoryComplianceService:
    if "repository_compliance_serivce" not in g:
        g.repository_compliance_serivce = RepositoryComplianceService(
            get_asset_service()
        )
    return g.repository_compliance_serivce
