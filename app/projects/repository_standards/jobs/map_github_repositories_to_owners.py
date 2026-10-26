import logging
from time import perf_counter
from typing import List

from app.app import create_app
from app.projects.repository_standards.models.repository_info import RepositoryInfo
from app.projects.repository_standards.config.collection_config import (
    parse_organisation_installations,
)
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


def _save_organisation(
    repositories: List[RepositoryInfo], owners_config,
    asset_service: AssetService, owner_service: OwnerService,
    organisation: str, collection_complete: bool, visibility: str,
):
    assets_by_repository = {}
    for repository in repositories:
        key = (repository.basic.organisation, repository.basic.name)
        assets_by_repository[key] = asset_service.update_asset_by_name(
            repository.basic.name,
            repository.to_dict(),
            organisation=repository.basic.organisation,
        )

    for owner_config in owners_config:
        if owner_config.config.organisation != organisation:
            continue
        logger.info(f"Mapping Repositories for Owner [ {owner_config.name} ]")

        owners = owner_service.find_by_name(owner_config.name)
        if not owners or len(owners) == 0:
            logger.error(f"Owner [ {owner_config.name} ] not found")
            continue
        owner = owners[0]

        for repository in repositories:
            logger.debug(f"Mapping Repository [ {repository.basic.name} ]")

            if repository.basic.organisation != owner_config.config.organisation:
                continue

            asset = assets_by_repository[
                (repository.basic.organisation, repository.basic.name)
            ]

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

    if collection_complete:
        asset_service.remove_stale_assets([organisation], visibility)
        asset_service.remove_stale_relationships([organisation], visibility)


def main():
    configure_logging(app_config.logging_level)
    logger.info("Running...")

    asset_service = AssetService(AssetRepository())
    owner_service = OwnerService(OwnerRepository())
    installations = parse_organisation_installations(
        app_config.github.repository_standards_orgs,
        app_config.github.app.installation_id,
    )
    owners_config = owner_service.find_all()
    if not owners_config:
        logger.info("No owners found; collected repositories will remain unowned")

    repository_count = 0
    collection_seconds = 0.0
    mapping_seconds = 0.0
    visibility = app_config.github.repository_visibility
    for installation in installations:
        remaining_limit = max(0, app_config.github.repository_limit - repository_count)
        if remaining_limit == 0:
            logger.warning(
                "Repository limit reached before collecting organization=%s",
                installation.organisation,
            )
            break
        logger.info("Organization collection starting: organisation=%s", installation.organisation)
        collection_started = perf_counter()
        github_service = GithubService(
            app_config.github.app.client_id,
            app_config.github.app.private_key,
            installation.installation_id,
            organisation_name=installation.organisation,
        )
        repositories = github_service.get_repositories(
            workers=app_config.github.collection_workers,
            visibility=visibility,
            limit=remaining_limit,
        )
        collection_elapsed = perf_counter() - collection_started
        collection_seconds += collection_elapsed
        repository_count += len(repositories)
        collection_complete = len(repositories) < remaining_limit
        if not collection_complete:
            logger.warning(
                "Repository cap reached for organisation=%s; skipping stale cleanup",
                installation.organisation,
            )
        logger.info(
            "Organization collection complete: organisation=%s repositories=%s elapsed=%.2fs",
            installation.organisation, len(repositories), collection_elapsed,
        )
        mapping_started = perf_counter()
        _save_organisation(
            repositories, owners_config, asset_service, owner_service,
            installation.organisation, collection_complete, visibility,
        )
        mapping_elapsed = perf_counter() - mapping_started
        mapping_seconds += mapping_elapsed
        logger.info(
            "Organization save complete: organisation=%s repositories=%s cleanup=%s elapsed=%.2fs",
            installation.organisation, len(repositories), collection_complete, mapping_elapsed,
        )

    logger.info(
        "Collection phase complete: repositories=%s workers=%s elapsed=%.2fs",
        repository_count, app_config.github.collection_workers, collection_seconds,
    )
    logger.info("Mapping and cleanup complete: elapsed=%.2fs", mapping_seconds)
    logger.info("Complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
