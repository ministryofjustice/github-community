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
        logo = "iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAMAAAC7IEhfAAAAflBMVEULDAwaGxsbGxsbHBwpKioqKioqKys5OTk5OjpISEhISUlJSUlXWFhYWFhYWVlmZ2dnZ2dnaGh1dnZ2dnZ2d3eEhYWFhYWFhoaUlJSUlZWVlZWjo6OjpKSkpKSys7Ozs7PBwsLCwsLDw8PR0dHR0tLS0tLg4ODh4eHw8PD////0W6DbAAACOElEQVQYGdXB4XYbJxAG0A8pi6YYuqPMdlgiLETWK+D9X7Cpj6PjpO2J/+Ze/KaOFh8j1eJDfDL4iOPaLH7NiqyqQvgFK0zz8+RCAODwv47MgBRg4gAYh39z+If3Ro1P1jJ5A5Az+Nmn4AwgLNvzbSv3QskArkbCj0zgwBNMdtWtNWQWxpS3dl/xE82XnYG6pZK5yd4NPt/a6JXwQLAwpeZrNeBS9t56ah7gKNso4Qhr8MrfdwepeW0BVNcYgvdZgDmke8+Ua8Gb5Cu4llztE2fSmJxNLlH05FOUXDzeTFhh4ku7VQ5x8fQnLJ6ClD7U4WImPAjDtvv4OrHzvLgzK7v1cq9juCMpHripbWMbPX8+XXPiSOK4nNIYoxcnjDfaV7uPfl/62J7nWf44k7Ct6lwbo2juweDVqnYdbQJiTrprCtHNjjM5QFqPPm54ZRKkjTp7eJl5Cecnf37y56xneL1+rQy1eMW3KKOPsbJ6f02UtGlSJubRK+dUVrwhuDF0fHGBXdI5Srkkr+yWEbkxToTvtO8xNeeE/e7nL7roykJh7lzKTnigez9M22hbnJVilnQtgVZdCfN0qBMeaG9AKNcqs5bMkywiM7sDsAAZ77ShHjg4TEUNO9GjygGASfAveG/ZEgCaZ7nQRDL75Gd3BHkqJ7znLqpx3/NLlyl4yKnlOZdvtgvhPTfyKlteVBKckYlUpbTntcR9wg+WKP4AwMbtL5K6Eb4h1nzGfzPrlpzetoAPOOA39TfuoTeEaSFm3gAAAABJRU5ErkJggg=="
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

        return f"https://img.shields.io/badge/{quote(label)}-{quote(message)}-{color}?style=for-the-badge&labelColor=0b0c0c&logo=data:image/png;base64,{logo}"


def get_repository_compliance_service() -> RepositoryComplianceService:
    if "repository_compliance_serivce" not in g:
        g.repository_compliance_serivce = RepositoryComplianceService(
            get_asset_service()
        )
    return g.repository_compliance_serivce
