from typing import List

from flask import g

from app.projects.repository_standards.repositories.owner_repository import (
    OwnerRepository,
    OwnerView,
    get_owner_repository,
)


class OwnerService:
    def __init__(self, owner_repository: OwnerRepository):
        self.__owner_repository = owner_repository

    def get_by_id(self, id: str) -> OwnerView | None:
        owner = self.__owner_repository.find_by_id(id)

        if owner:
            return OwnerView.from_owner(owner)

    def find_by_name(self, owner_name: str) -> List[OwnerView]:
        owners = self.__owner_repository.find_by_name(owner_name)
        return [OwnerView.from_owner(owner) for owner in owners]

    def update_by_id(
        self, id: str, name: str, owner_teams: List[str]
    ) -> OwnerView | None:
        owner = self.__owner_repository.update_by_id(id, name, owner_teams)

        if owner:
            return OwnerView.from_owner(owner)

    def add_team_owner(self, name: str, owner_teams: List[str]) -> OwnerView | None:
        owner = self.__owner_repository.add_team_owner(name, owner_teams)

        if owner:
            return OwnerView.from_owner(owner)


def get_owner_service() -> OwnerService:
    if "owner_service" not in g:
        g.owner_service = OwnerService(get_owner_repository())
    return g.owner_service
