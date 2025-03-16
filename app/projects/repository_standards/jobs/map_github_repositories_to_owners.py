import logging
from typing import List

from app.app import create_app
from app.projects.repository_standards.models.repository_info import RepositoryInfo
from app.projects.repository_standards.repositories.asset_repository import (
    AssetRepository,
)
from app.projects.repository_standards.repositories.owner_repository import (
    OwnerRepository,
)
from app.projects.repository_standards.services.asset_service import AssetService
from app.projects.repository_standards.services.github_service import GithubService
from app.shared.config.app_config import app_config
from app.shared.config.logging_config import configure_logging

logger = logging.getLogger(__name__)


def contains_one_or_more(values: list[str], lists_to_check: list[list[str]]) -> bool:
    found = False

    for value in values:
        for list_to_check in lists_to_check:
            if value in list_to_check:
                found = True

    return found


def main(
    owners=[
        {
            "name": "HMPPS",
            "teams": ["HMPPS Developers"],
            "prefix": "hmpps-",
        },
        {
            "name": "LAA",
            "teams": [
                "LAA Admins",
                "LAA Technical Architects",
                "LAA Developers",
                "LAA Crime Apps team",
                "LAA Crime Apply",
                "laa-eligibility-platform",
                "LAA Get Access",
                "LAA Payments and Billing",
            ],
            "prefix": "laa-",
        },
        {
            "name": "OPG",
            "teams": ["OPG"],
            "prefix": "opg-",
        },
        {
            "name": "CICA",
            "teams": ["CICA"],
            "prefix": "cica-",
        },
        {
            "name": "Central Digital",
            "teams": [
                "Central Digital Product Team",
                "tactical-products",
                # Data Platforms
                "analytical-platform",
                "data-engineering",
                "analytics-hq",
                "data-catalogue",
                "data-platform",
                "data-and-analytics-engineering",
                "observability-platform",
                # Publishing Platforms
                "Form Builder",
                "Hale platform",
                "JOTW Content Devs",
            ],
            "prefix": "bichard7",
        },
        {
            "name": "Platforms",
            "teams": [
                # Hosting Platforms
                "modernisation-platform",
                "operations-engineering",
                "aws-root-account-admin-team",
                "WebOps",  # Cloud Platform
                "Studio Webops",  # Digital Studio Operations (DSO)
            ],
        },
        {
            "name": "Technology Services",
            "teams": [
                "nvvs-devops-admins",
                "moj-official-techops",
                "cloud-ops-alz-admins",
            ],
        },
    ],
):
    configure_logging(app_config.logging_level)
    logger.info("Running...")

    asset_service = AssetService(AssetRepository())
    owner_repository = OwnerRepository()
    github_service = GithubService(
        app_config.github.app.client_id,
        app_config.github.app.private_key,
        app_config.github.app.installation_id,
    )

    repositories: List[RepositoryInfo] = github_service.get_all_repositories(limit=1)

    for owner in owners:
        logger.info(f"Mapping Repositories for Owner [ {owner} ]")
        name = owner["name"]
        teams = owner["teams"]
        prefix = owner.get("prefix")

        for repository in repositories:
            logger.info(f"Mapping Repository [ {repository} ]")

            repository_name_starts_with_prefix = (
                repository.basic.name.startswith(prefix)
                if prefix is not None
                else False
            )

            owner = owner_repository.find_by_name(name)[0]
            asset = asset_service.update_asset_by_name(
                repository.basic.name, repository
            )

            if contains_one_or_more(
                teams,
                [
                    repository.access.teams_with_admin,
                    repository.access.teams_with_admin_parents,
                ],
            ):
                asset_service.update_relationships_with_owner(
                    asset, owner, "ADMIN_ACCESS"
                )
            elif (
                contains_one_or_more(
                    teams,
                    [
                        repository.access.teams,
                        repository.access.teams_parents,
                    ],
                )
                or repository_name_starts_with_prefix
            ):
                asset_service.update_relationships_with_owner(asset, owner, "OTHER")

    logger.info("Complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
