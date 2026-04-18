from typing import List

from flask import g
from sqlalchemy import func
from sqlalchemy.orm import scoped_session

from app.projects.repository_standards.db_models import Owner, Relationship, db
from app.projects.repository_standards.models.owner import OwnerConfig


class OwnerView:
    def __init__(self, id: int, name: str, type: str, config: OwnerConfig):
        self.id = id
        self.name = name
        self.type = type
        self.config = config

    @classmethod
    def from_owner(cls, owner: Owner):
        return cls(
            id=owner.id,
            name=owner.name,
            type=owner.type.name,
            config=OwnerConfig.from_dict(owner.config),
        )


class OwnerRepository:
    def __init__(self, db_session: scoped_session = db.session):
        self.db_session = db_session

    def find_all(self) -> List[Owner]:
        owners = self.db_session.query(Owner).all()

        return owners

    def find_all_by_type_id(self, type_id: int) -> List[Owner]:
        owners = self.db_session.query(Owner).filter(Owner.type_id == type_id).all()

        return owners

    def find_by_name(self, name: str) -> List[Owner]:
        owners = (
            self.db_session.query(Owner)
            .filter(func.lower(Owner.name) == name.lower())
            .all()
        )

        return owners

    def find_by_id(self, id: str) -> Owner | None:
        owner = self.db_session.query(Owner).filter(Owner.id == id).first()

        return owner

    def find_all_business_units(self) -> List[Owner]:
        return self.find_all_by_type_id(type_id=1)

    def find_all_teams(self) -> List[Owner]:
        owners = self.find_all_by_type_id(type_id=2)

        return owners

    def add_team_owner(self, owner_name: str, owner_teams: List[str]) -> Owner:
        owner = Owner()
        owner.name = owner_name
        owner.type_id = 2
        owner.config = OwnerConfig(
            name=owner_name, teams=owner_teams, prefix=""
        ).to_dict()
        self.db_session.add(owner)
        self.db_session.commit()
        return owner

    def update_by_id(
        self, id: str, owner_name: str, owner_teams: List[str]
    ) -> Owner | None:
        owner = self.find_by_id(id)
        if not owner:
            return None
        owner.name = owner_name
        owner.config = OwnerConfig(
            name=owner_name, teams=owner_teams, prefix=""
        ).to_dict()
        self.db_session.add(owner)
        self.db_session.commit()
        return owner

    def delete_by_id(self, id: str) -> bool:
        owner = self.find_by_id(id)
        if not owner:
            return False
        self.db_session.query(Relationship).filter(
            Relationship.owners_id == owner.id
        ).delete(synchronize_session=False)
        self.db_session.delete(owner)
        self.db_session.commit()
        return True


def get_owner_repository() -> OwnerRepository:
    if "owner_repository" not in g:
        g.owner_repository = OwnerRepository()
    return g.owner_repository
