from app.projects.repository_standards.repositories.asset_repository import AssetRepository
from app.projects.repository_standards.repositories.owner_repository import OwnerRepository
import logging
from app.shared.config.app_config import app_config
from app.projects.repository_standards.config.logging_config import configure_logging
from app.projects.repository_standards.services.github_service import GithubService
from app.projects.repository_standards.services.asset_service import AssetService
from app.app import create_app

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
            "name": "CTO Office",
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
            "name": "Tech Services",
            "teams": ["nvvs-devops-admins", "moj-official-techops"],
        },
        {
            "name": "Operations Engineering",
            "teams": ["operations-engineering"],
            "prefix": "operations-engineering-",
        },
        {
            "name": "Modernisation Platform",
            "teams": ["modernisation-platform"],
            "prefix": "modernisation-platform-",
        },
    ],
):
    configure_logging(app_config.logging_level)
    logger.info("Running...")

    asset_service = AssetService(AssetRepository())
    owner_repository = OwnerRepository()
    github_service = GithubService(app_config.github.token)

    repositories = github_service.get_all_repositories()

    for owner in owners:
        logger.info(f"Mapping Repositories for Owner [ {owner} ]")
        name = owner["name"]
        teams = owner["teams"]
        prefix = owner.get("prefix")

        for repository in repositories:
            logger.info(f"Mapping Repository [ {repository} ]")
            github_teams_with_admin_access = repository[
                "github_teams_with_admin_access"
            ]
            github_teams_with_admin_access_parents = repository[
                "github_teams_with_admin_access_parents"
            ]
            github_teams_with_any_access = repository["github_teams_with_any_access"]
            github_teams_with_any_access_parents = repository[
                "github_teams_with_any_access_parents"
            ]
            repository_name = repository["name"]
            teams_with_admin_access = [
                github_teams_with_admin_access,
                github_teams_with_admin_access_parents,
            ]
            teams_with_any_access = [
                github_teams_with_any_access,
                github_teams_with_any_access_parents,
            ]
            repository_name_starts_with_prefix = (
                repository_name.startswith(prefix) if prefix is not None else False
            )

            owner = owner_repository.find_by_name(name)[0]
            asset = asset_service.add_if_name_does_not_exist(repository_name)

            if contains_one_or_more(teams, teams_with_admin_access):
                asset_service.update_relationships_with_owner(
                    asset, owner, "ADMIN_ACCESS"
                )
            elif (
                contains_one_or_more(teams, teams_with_any_access)
                or repository_name_starts_with_prefix
            ):
                asset_service.update_relationships_with_owner(asset, owner, "OTHER")

    logger.info("Complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
