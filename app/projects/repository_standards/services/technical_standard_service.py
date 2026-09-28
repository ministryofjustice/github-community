from typing import List

from flask import g

from app.projects.repository_standards.config.technical_standard_config import (
    FAIL,
    get_all_technical_standard_checks,
)
from app.projects.repository_standards.models.technical_standard import (
    TechnicalStandardReportView,
)
from app.projects.repository_standards.repositories.asset_repository import (
    RepositoryView,
)
from app.projects.repository_standards.services.asset_service import (
    AssetService,
    get_asset_service,
)


class TechnicalStandardService:
    def __init__(self, asset_service: AssetService):
        self.__asset_service = asset_service

    def __get_authoritative_owners(
        self, repository: RepositoryView, owners: List[str]
    ) -> List[str]:
        return [
            owner
            for owner in owners
            if self.__asset_service.is_owner_authoritative_for_repository(
                repository, owner
            )
        ]

    def __get_report(self, repository: RepositoryView) -> TechnicalStandardReportView:
        business_unit_owners = self.__get_authoritative_owners(
            repository, repository.business_unit_owners_names
        )
        team_owners = self.__get_authoritative_owners(
            repository, repository.team_owners_names
        )
        checks = get_all_technical_standard_checks(
            repository, business_unit_owners or team_owners
        )

        return TechnicalStandardReportView(
            name=repository.name,
            # not_checked is excluded until every check is implemented
            compliant=all(check.status != FAIL for check in checks),
            checks=checks,
            authoritative_business_unit_owners=business_unit_owners,
            authoritative_team_owners=team_owners,
            description=repository.data.basic.description,
        )

    def get_all_repositories(self) -> List[TechnicalStandardReportView]:
        return [
            self.__get_report(repository)
            for repository in self.__asset_service.get_all_repositories()
        ]

    def get_repository_by_name(self, name: str) -> TechnicalStandardReportView | None:
        repository = self.__asset_service.get_repository_by_name(name)
        return self.__get_report(repository) if repository else None


def get_technical_standard_service() -> TechnicalStandardService:
    if "technical_standard_service" not in g:
        g.technical_standard_service = TechnicalStandardService(get_asset_service())
    return g.technical_standard_service