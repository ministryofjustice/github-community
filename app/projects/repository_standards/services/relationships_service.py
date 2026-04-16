import logging
from typing import List

from flask import g

from app.projects.repository_standards.repositories.owner_repository import OwnerView
from app.projects.repository_standards.services.asset_service import (
    AssetService,
    get_asset_service,
)
from app.projects.repository_standards.services.owner_service import (
    OwnerService,
    get_owner_service,
)

logger = logging.getLogger(__name__)


class RelationshipsService:
    def __init__(self, owner_service: OwnerService, asset_service: AssetService):
        self.__owner_service = owner_service
        self.__asset_service = asset_service

    def __contains_one_or_more(
        self, values: List[str], list_to_check: List[str]
    ) -> bool:
        return any(value in list_to_check for value in values)
    def update_relationship_for_owner(self, owner: OwnerView) -> None:
        logger.info(f"Mapping Repositories for Owner [ {owner.name} ]")

        repositories = self.__asset_service.get_all_repositories()
        for repository in repositories:
            logger.debug(f"Mapping Repository [ {repository.name} ]")

            asset = self.__asset_service.find_asset_by_id(repository.id)
            if asset is None:
                logger.error(f"Missing Asset ID [ {repository.id} ]")
                continue

            repository_name_starts_with_prefix = (
                repository.name.startswith(owner.config.prefix)
                if owner.config.prefix
                else False
            )

            if self.__contains_one_or_more(
                owner.config.teams,
                repository.data.access.teams_with_admin,
            ):
                self.__asset_service.update_relationships_with_owner(
                    asset, owner, "ADMIN_ACCESS"
                )
            elif (
                self.__contains_one_or_more(
                    owner.config.teams,
                    repository.data.access.teams,
                )
                or repository_name_starts_with_prefix
            ):
                self.__asset_service.update_relationships_with_owner(
                    asset, owner, "OTHER"
                )


def get_relationships_service() -> RelationshipsService:
    if "relationships_service" not in g:
        g.relationships_service = RelationshipsService(
            get_owner_service(), get_asset_service()
        )
    return g.relationships_service
