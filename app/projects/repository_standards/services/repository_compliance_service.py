import logging
from app.projects.repository_standards.services.asset_service import AssetService
from app.projects.repository_standards.repositories.asset_repository import (
    AssetView,
)
from flask import g
from typing import List

from app.projects.repository_standards.services.asset_service import get_asset_service


class RepositoryComplianceCheck:
    def __init__(self, name: str, status: str):
        self.name = name
        self.status = status


class RepositoryComplianceReportView:
    def __init__(
        self,
        name: str,
        compliance_status: str,
        authorative_owner: str | None,
        checks: List[RepositoryComplianceCheck],
    ):
        self.name = name
        self.compliance_status = compliance_status
        self.authorative_owner = authorative_owner
        self.checks = checks


class RepositoryComplianceService:
    def __init__(self, asset_service: AssetService):
        self.__asset_service = asset_service

    def get_repository_compliance_report(
        self,
        asset: AssetView,
    ) -> RepositoryComplianceReportView:
        authorative_owner = [
            owner
            for owner in asset.owner_names
            if self.__asset_service.is_owner_authoritative_for_repository(asset, owner)
        ]

        checks = [
            RepositoryComplianceCheck(
                name="Has an Authorative Owner",
                status="pass" if len(authorative_owner) > 0 else "fail",
            ),
            RepositoryComplianceCheck(
                name="License is MIT",
                status="pass" if asset.data.get("license") == "mit" else "fail",
            ),
            RepositoryComplianceCheck(
                name="Default Branch is main",
                status="pass"
                if asset.data.get("default_branch_name") == "main"
                else "fail",
            ),
        ]

        compliance_status = (
            "pass" if all(check.status == "pass" for check in checks) else "fail"
        )

        return RepositoryComplianceReportView(
            name=asset.name,
            compliance_status=compliance_status,
            authorative_owner=authorative_owner[0]
            if len(authorative_owner) > 0
            else None,
            checks=checks,
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


def get_repository_compliance_service() -> RepositoryComplianceService:
    if "repository_compliance_serivce" not in g:
        g.repository_compliance_serivce = RepositoryComplianceService(
            get_asset_service()
        )
    return g.repository_compliance_serivce
