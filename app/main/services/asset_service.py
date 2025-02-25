import logging
from app.main.models import Asset, Owner
from app.main.repositories.asset_repository import (
    AssetRepository,
    get_asset_repository,
    AssetView,
)
from flask import g
from typing import List


class AssetService:
    def __init__(self, asset_repository: AssetRepository):
        self.__asset_repository = asset_repository

    def get_all_repositories(self) -> List[AssetView]:
        repositories = self.__asset_repository.find_all()
        return repositories

    def get_repositories_by_authoratative_owner(
        self,
        owner_to_filter_by: str,
    ) -> List[AssetView]:
        repositories = self.__asset_repository.find_all_by_owner(owner_to_filter_by)
        response = [
            repo
            for repo in repositories
            if self.is_owner_authoritative_for_repository(repo, owner_to_filter_by)
        ]
        return response

    def get_repositories_by_authoratative_owner_filtered_by_missing_admin_access(
        self, owner_to_filter_by: str
    ) -> list[AssetView]:
        repositories = self.get_repositories_by_authoratative_owner(owner_to_filter_by)

        repositories_missing_admin_access = [
            repository
            for repository in repositories
            if owner_to_filter_by not in repository.admin_owner_names
        ]

        return repositories_missing_admin_access

    def is_owner_authoritative_for_repository(
        self, repository: AssetView, owner_to_filter_by: str
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

    def add_asset(self, name: str, type: str):
        asset = self.__asset_repository.add_asset(name=name, type=type)
        return asset

    def create_relationship(self, asset: Asset, owner: Owner, relationship_type: str):
        relationship = self.__asset_repository.create_relationship(
            asset, owner, relationship_type
        )
        return relationship

    def clean_all_tables(self):
        self.__asset_repository.clean_all_tables()

    def update_relationships_with_owner(
        self, asset: Asset, owner: Owner, relationship_type: str
    ):
        self.__asset_repository.update_relationship_with_owner(
            asset, owner, relationship_type
        )

    def add_if_name_does_not_exist(self, name: str) -> Asset:
        assets = self.__asset_repository.find_by_name(name)

        if len(assets) > 1:
            raise ValueError(
                f"Multiple Repositories Named [ {name} ] - Remove The Duplicates"
            )

        if len(assets) == 1:
            logging.debug(f"Found existing respoistory with ID [ {assets[0].id} ]")
            return assets[0]

        logging.info(f"No repository found [ {name} ] - creating a new asset...")
        return self.__asset_repository.add_asset(name, "REPOSITORY")

    def get_repository_by_name(self, name: str) -> AssetView:
        asset = self.__asset_repository.find_by_name(name)
        return AssetView.from_asset(asset[0])


def get_asset_service() -> AssetService:
    if "asset_service" not in g:
        g.asset_service = AssetService(get_asset_repository())
    return g.asset_service
