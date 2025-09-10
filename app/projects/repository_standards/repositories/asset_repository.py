import logging
from datetime import datetime, timedelta
from typing import List

from flask import g
from sqlalchemy.orm import scoped_session

from app.projects.repository_standards.db_models import Asset, Owner, Relationship, db
from app.projects.repository_standards.models.repository_info import RepositoryInfo


class RepositoryView:
    def __init__(
        self,
        name: str,
        owner_names: List[str],
        admin_owner_names: List[str],
        business_unit_owner_names: List[str],
        business_unit_admin_owner_names: List[str],
        team_owner_names: List[str],
        team_admin_owner_names: List[str],
        data: RepositoryInfo,
    ):
        self.name = name
        self.admin_owner_names = admin_owner_names
        self.owner_names = owner_names
        self.business_unit_owners_names = business_unit_owner_names
        self.business_unit_admin_owners_names = business_unit_admin_owner_names
        self.team_owners_names = team_owner_names
        self.team_admin_owners_names = team_admin_owner_names
        self.data = data

    @classmethod
    def from_asset(cls, asset: Asset):
        owners = [relationship.owner for relationship in asset.relationships]
        admin_owners = [
            relationship.owner
            for relationship in asset.relationships
            if "ADMIN_ACCESS" in relationship.type
        ]

        return cls(
            name=asset.name,
            owner_names=[owner.name for owner in owners],
            admin_owner_names=[
                owner.name for owner in owners if owner.type.name == "ADMIN"
            ],
            business_unit_owner_names=[
                owner.name for owner in owners if owner.type.name == "BUSINESS_UNIT"
            ],
            business_unit_admin_owner_names=[
                owner.name
                for owner in admin_owners
                if owner.type.name == "BUSINESS_UNIT"
            ],
            team_owner_names=[
                owner.name for owner in owners if owner.type.name == "TEAM"
            ],
            team_admin_owner_names=[
                owner.name for owner in admin_owners if owner.type.name == "TEAM"
            ],
            data=RepositoryInfo.from_dict(asset.data),
        )


class AssetRepository:
    def __init__(self, db_session: scoped_session = db.session):
        self.db_session = db_session

    def find_all(self) -> list[RepositoryView]:
        assets = self.db_session.query(Asset).all()

        return [RepositoryView.from_asset(asset) for asset in assets]

    def find_all_by_owners(self, owner_names: list[str]) -> list[RepositoryView]:
        assets = (
            self.db_session.query(Asset)
            .join(Asset.relationships.owners)
            .filter(Owner.name.in_(owner_names))
            .distinct()
            .all()
        )

        return [RepositoryView.from_asset(asset) for asset in assets]

    def find_all_by_owner(self, owner_name: str) -> list[RepositoryView]:
        assets = (
            self.db_session.query(Asset)
            .join(Asset.relationships.owners)
            .filter(Asset.relationships.owners.any(name=owner_name))
            .all()
        )

        return [RepositoryView.from_asset(asset) for asset in assets]

    def add_asset(self, name: str, type: str, data: dict) -> Asset:
        asset = Asset()
        asset.name = name
        asset.type = type
        asset.last_updated = datetime.now()
        asset.data = data
        self.db_session.add(asset)
        self.db_session.commit()
        return asset

    def create_relationship(
        self, asset: Asset, owner: Owner, relationship_type: str
    ) -> Relationship:
        relationship = Relationship()
        relationship.owners_id = owner.id
        relationship.assets_id = asset.id
        relationship.type = relationship_type
        self.db_session.add(relationship)
        self.db_session.commit()
        return relationship

    def find_by_name(self, name: str) -> List[Asset]:
        assets = self.db_session.query(Asset).filter(Asset.name == name).all()
        return assets

    def update_relationship_with_owner(
        self, asset: Asset, owner: Owner, relationship_type: str
    ) -> Relationship:
        relationships = (
            self.db_session.query(Relationship)
            .filter_by(assets_id=asset.id, owners_id=owner.id)
            .all()
        )

        if len(relationships) > 1:
            raise ValueError(
                f"Asset [ {asset.name} ] has multiple relationships with Owner [ {owner.name} ]"
            )

        if len(relationships) == 0:
            logging.info(
                f"Asset [ {asset.name} ] has no relationships with [ {owner.name} ] - creating new relationship [ {relationship_type} ] "
            )
            return self.create_relationship(asset, owner, relationship_type)

        relationship = relationships[0]

        if relationship.type == relationship_type:
            logging.info(
                f"No relationship change between Asset [ {asset.name} ] and Owner [ {owner.name} ] - skipping"
            )
            return relationship

        logging.info(
            f"Asset [ {asset.name} ] has one relationships with [ {owner.name} ] - updating relationship from [ {relationship.type} ] to new relationship [ {relationship_type} ] "
        )
        relationship.type = relationship_type
        self.db_session.commit()

        return relationship

    def update_by_name(self, name: str, data: dict) -> Asset:
        assets = self.find_by_name(name)

        if len(assets) > 1:
            raise ValueError(
                f"Multiple Repositories Named [ {name} ] - Remove The Duplicates"
            )

        if len(assets) == 0:
            logging.info(f"No repository found [ {name} ] - creating a new asset...")
            return self.add_asset(name, "REPOSITORY", data)

        asset = assets[0]
        logging.info(
            f"Found existing respoistory with ID [ {asset.id} ] - updating existing assets data..."
        )
        asset.last_updated = datetime.now()
        asset.data = data
        self.db_session.commit()

        return assets[0]

    def remove_stale_assets(self):
        stale_assets = self.db_session.query(Asset).filter(
            Asset.last_updated < datetime.today() - timedelta(days=1)
        )
        for asset in stale_assets:
            logging.info(f"Removing stale asset: {asset.name}")
            self.db_session.query(Relationship).filter_by(assets_id=asset.id).delete()
            self.db_session.delete(asset)

        self.db_session.commit()


def get_asset_repository() -> AssetRepository:
    if "asset_repository" not in g:
        g.asset_repository = AssetRepository()
    return g.asset_repository
