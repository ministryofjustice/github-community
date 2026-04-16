import logging
from typing import List

from app.app import create_app
from app.projects.repository_standards.models.repository_info import RepositoryInfo
from app.projects.repository_standards.services.repository_compliance_service import (
    RepositoryComplianceService,
)
from app.projects.repository_standards.repositories.asset_repository import (
    AssetRepository,
)
from app.projects.repository_standards.repositories.owner_repository import (
    OwnerRepository,
)
from app.projects.repository_standards.services.asset_service import AssetService
from app.projects.repository_standards.services.github_service import GithubService
from app.projects.repository_standards.config.repository_compliance_config import (
    get_repository_standard_from_maturity_level,
)
from app.shared.config.app_config import app_config
from app.shared.config.logging_config import configure_logging
from app.projects.repository_standards.config.owners_config import owners_config

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
    repository_compliance_service = RepositoryComplianceService(asset_service)
    owner_repository = OwnerRepository()
    github_service = GithubService(
        app_config.github.app.client_id,
        app_config.github.app.private_key,
        app_config.github.app.installation_id,
    )

    repositories: List[RepositoryInfo] = github_service.get_all_repositories()
    owner_by_config_name = {}

    for owner_config in owners_config:
        owners = owner_repository.find_by_name(owner_config.name)
        if not owners or len(owners) == 0:
            logger.error(f"Owner [ {owner_config.name} ] not found")
            continue
        owner_by_config_name[owner_config.name] = owners[0]

    custom_property_update_counters = {
        "attempted_updates": 0,
        "successful_updates": 0,
        "failed_updates": 0,
        "skipped_updates": 0,
    }

    for repository in repositories:
        logger.debug(f"Mapping Repository [ {repository.basic.name} ]")

        asset = asset_service.update_asset_by_name(
            repository.basic.name, repository.to_dict()
        )

        compliance_report = repository_compliance_service.get_repository_by_name(
            repository.basic.name
        )
        repository_standard = (
            get_repository_standard_from_maturity_level(compliance_report.maturity_level)
            if compliance_report
            else None
        )

        repository.basic.repository_standard = repository_standard
        asset = asset_service.update_asset_by_name(
            repository.basic.name, repository.to_dict()
        )

        if not compliance_report:
            custom_property_update_counters["skipped_updates"] += 1
            logger.warning(
                "Skipping repository-standard update: no compliance report for repository [ %s ]",
                repository.basic.name,
            )
        elif not repository_standard:
            custom_property_update_counters["skipped_updates"] += 1
            logger.info(
                "Skipping repository-standard update: maturity level does not map to a custom property value for repository [ %s ]",
                repository.basic.name,
            )
        else:
            custom_property_update_counters["attempted_updates"] += 1
            try:
                github_service.set_repository_standard_custom_property(
                    repository.basic.name,
                    repository_standard,
                )
                custom_property_update_counters["successful_updates"] += 1
            except Exception as error:
                custom_property_update_counters["failed_updates"] += 1
                logger.error(
                    "Failed to update repository-standard custom property for repository [ %s ]: %s",
                    repository.basic.name,
                    error,
                )

        for owner_config in owners_config:
            owner = owner_by_config_name.get(owner_config.name)
            if not owner:
                continue

            repository_name_starts_with_prefix = (
                repository.basic.name.startswith(owner_config.prefix)
                if owner_config.prefix is not None
                else False
            )

            if contains_one_or_more(
                owner_config.teams,
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
                    owner_config.teams,
                    [
                        repository.access.teams,
                        repository.access.teams_parents,
                    ],
                )
                or repository_name_starts_with_prefix
            ):
                asset_service.update_relationships_with_owner(asset, owner, "OTHER")

    logger.info(
        "Repository custom property update summary: attempted=%d successful=%d failed=%d skipped=%d",
        custom_property_update_counters["attempted_updates"],
        custom_property_update_counters["successful_updates"],
        custom_property_update_counters["failed_updates"],
        custom_property_update_counters["skipped_updates"],
    )

    asset_service.remove_stale_assets()
    asset_service.remove_stale_relationships()

    logger.info("Complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
