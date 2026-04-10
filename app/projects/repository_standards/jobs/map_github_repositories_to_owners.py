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
from app.projects.repository_standards.services.owner_service import (
    OwnerService,
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


def main():
    configure_logging(app_config.logging_level)
    logger.info("Running...")

    asset_service = AssetService(AssetRepository())
    owner_service = OwnerService(OwnerRepository())
    github_service = GithubService(
        app_config.github.app.client_id,
        app_config.github.app.private_key,
        app_config.github.app.installation_id,
    )

    owners_config = owner_service.find_all()
    if not owners_config:
        logger.info("No owners found, exitting early")
        return

    repositories: List[RepositoryInfo] = github_service.get_repositories()

    for owner_config in owners_config:
        logger.info(f"Mapping Repositories for Owner [ {owner_config.name} ]")

        owners = owner_service.find_by_name(owner_config.name)
        if not owners or len(owners) == 0:
            logger.error(f"Owner [ {owner_config.name} ] not found")
            continue
        owner = owners[0]

        for repository in repositories:
            logger.debug(f"Mapping Repository [ {repository.basic.name} ]")

            asset = asset_service.update_asset_by_name(
                repository.basic.name, repository.to_dict()
            )

            repository_name_starts_with_prefix = (
                repository.basic.name.startswith(owner_config.config.prefix)
                if owner_config.config.prefix
                else False
            )

            if contains_one_or_more(
                owner_config.config.teams,
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
                    owner_config.config.teams,
                    [
                        repository.access.teams,
                        repository.access.teams_parents,
                    ],
                )
                or repository_name_starts_with_prefix
            ):
                asset_service.update_relationships_with_owner(asset, owner, "OTHER")

    asset_service.remove_stale_assets()
    asset_service.remove_stale_relationships()

    logger.info("Complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
