from app.main.models import db, Owner
from flask import g
from sqlalchemy.orm import scoped_session
from typing import List


class OwnerView:
    def __init__(self, name: str):
        self.name = name

    @classmethod
    def from_owner(cls, asset: Owner):
        return cls(
            name=asset.name,
        )


class OwnerRepository:
    def __init__(self, db_session: scoped_session = db.session):
        self.db_session = db_session

    def find_all(self) -> List[OwnerView]:
        owners = self.db_session.query(Owner).all()

        return [OwnerView.from_owner(owner) for owner in owners]

    def find_by_name(self, name: str) -> List[Owner]:
        owners = self.db_session.query(Owner).filter(Owner.name == name).all()

        return owners

    def find_all_names(self) -> List[str]:
        owners = self.find_all()

        return [owner.name for owner in owners]

    def add_owner(self, owner_name: str) -> Owner:
        owner = Owner()
        owner.name = owner_name
        self.db_session.add(owner)
        self.db_session.commit()
        return owner


def get_owner_repository() -> OwnerRepository:
    if "owner_repository" not in g:
        g.owner_repository = OwnerRepository()
    return g.owner_repository
