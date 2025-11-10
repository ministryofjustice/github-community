from typing import List

from flask import g

from app.projects.repository_standards.db_models import Asset, Owner
from app.projects.repository_standards.repositories.asset_repository import (
    AssetRepository,
    RepositoryView,
    get_asset_repository,
)


class AssetService:
    def __init__(self, asset_repository: AssetRepository):
        self.__asset_repository = asset_repository

    def get_all_repositories(self) -> List[RepositoryView]:
        repositories = self.__asset_repository.find_all()
        return repositories

    def is_owner_authoritative_for_repository(
        self, repository: RepositoryView, owner_to_filter_by: str
    ) -> bool:
        owner_has_admin_access = bool(
            owner_to_filter_by in repository.admin_owner_names
        )
        owner_has_other_access = bool(owner_to_filter_by in repository.owner_names)
        no_repository_admins = len(repository.admin_owner_names) == 0

        has_authorative_ownership = bool(
            owner_has_admin_access or (owner_has_other_access and no_repository_admins)
        )

        return has_authorative_ownership

    def update_relationships_with_owner(
        self, asset: Asset, owner: Owner, relationship_type: str
    ):
        self.__asset_repository.update_relationship_with_owner(
            asset, owner, relationship_type
        )

    def update_asset_by_name(self, name: str, data: dict) -> Asset:
        return self.__asset_repository.update_by_name(name, data)

    def get_repository_by_name(self, name: str) -> RepositoryView | None:
        asset = self.__asset_repository.find_by_name(name)
        return RepositoryView.from_asset(asset[0]) if len(asset) > 0 else None

    def remove_stale_assets(self):
        self.__asset_repository.remove_stale_assets()

    def remove_stale_relationships(self):
        self.__asset_repository.remove_stale_assets()


def get_asset_service() -> AssetService:
    if "asset_service" not in g:
        g.asset_service = AssetService(get_asset_repository())
    return g.asset_service
