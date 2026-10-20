from typing import List

from flask import g

from app.projects.repository_standards.config.technical_standard_config import (
    FAIL,
    get_all_technical_standard_checks,
)
from app.projects.repository_standards.models.technical_standard import (
    TechnicalStandardReportView,
)
from app.projects.repository_standards.db_models import Owner
from app.projects.repository_standards.repositories.owner_repository import OwnerView
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
        checks = get_all_technical_standard_checks(repository)

        return TechnicalStandardReportView(
            name=repository.name,
            # not_checked is excluded until every check is implemented
            compliant=all(check.status != FAIL for check in checks),
            checks=checks,
            authoritative_business_unit_owners=business_unit_owners,
            authoritative_team_owners=team_owners,
            description=repository.data.basic.description,
            last_updated=getattr(repository, "last_updated", None),
            visibility=getattr(repository.data.basic, "visibility", None),
        )

    def get_all_repositories(self) -> List[TechnicalStandardReportView]:
        return [
            self.__get_report(repository)
            for repository in self.__asset_service.get_all_repositories()
        ]

    def get_check_summaries(
        self, repositories: List[TechnicalStandardReportView]
    ) -> list[dict]:
        repository_count = len(repositories)
        summaries = {}

        for repository in repositories:
            for check in repository.checks:
                summary = summaries.setdefault(
                    check.number,
                    {
                        "number": check.number,
                        "name": check.name,
                        "link_to_guidance": check.link_to_guidance,
                        "pass_count": 0,
                        "fail_count": 0,
                    },
                )
                if check.status == "pass":
                    summary["pass_count"] += 1
                elif check.status == FAIL:
                    summary["fail_count"] += 1

        for summary in summaries.values():
            summary["not_checked_count"] = (
                repository_count - summary["pass_count"] - summary["fail_count"]
            )
            summary["pass_rate"] = (
                summary["pass_count"] / repository_count * 100
                if repository_count
                else 0
            )

        return sorted(summaries.values(), key=lambda summary: summary["number"])

    def get_owner_counts(
        self, owners: List[Owner]
    ) -> dict[int, dict[str, int]]:
        counts = {
            owner.id: {"repo_count": 0, "compliant_count": 0}
            for owner in owners
        }
        if not owners:
            return counts

        owner_type = owners[0].type.name
        if owner_type == "BUSINESS_UNIT":
            owner_field_name = "authoritative_business_unit_owners"
        elif owner_type == "TEAM":
            owner_field_name = "authoritative_team_owners"
        else:
            raise ValueError(f"Unrecognised owner type: {owner_type}")

        owner_ids_by_name = {owner.name: owner.id for owner in owners}
        for repository in self.get_all_repositories():
            owner_ids = {
                owner_ids_by_name[name]
                for name in getattr(repository, owner_field_name)
                if name in owner_ids_by_name
            }
            for owner_id in owner_ids:
                counts[owner_id]["repo_count"] += 1
                if repository.compliant:
                    counts[owner_id]["compliant_count"] += 1

        return counts

    def get_repositories_for_owner(
        self, owner: OwnerView
    ) -> List[TechnicalStandardReportView]:
        if owner.type == "BUSINESS_UNIT":
            owner_field_name = "authoritative_business_unit_owners"
        elif owner.type == "TEAM":
            owner_field_name = "authoritative_team_owners"
        else:
            return []

        return [
            repository
            for repository in self.get_all_repositories()
            if owner.name in getattr(repository, owner_field_name)
        ]

    def get_unowned_repositories(self) -> List[TechnicalStandardReportView]:
        return [
            repository
            for repository in self.get_all_repositories()
            if not repository.authoritative_business_unit_owners
            and not repository.authoritative_team_owners
        ]

    def get_repository_by_name(self, name: str) -> TechnicalStandardReportView | None:
        repository = self.__asset_service.get_repository_by_name(name)
        return self.__get_report(repository) if repository else None


def get_technical_standard_service() -> TechnicalStandardService:
    if "technical_standard_service" not in g:
        g.technical_standard_service = TechnicalStandardService(get_asset_service())
    return g.technical_standard_service