"""Business unit and team ownership for the Repository Stats pages.

Reads the shared owners, owner_types, relationships and assets tables (maintained by
the Repository Standards ownership job) with read-only queries, so this project doesn't
import Repository Standards code. The rule matches
AssetService.is_owner_authoritative_for_repository() in Repository Standards: a business
unit is authoritative if it has admin access, or has any access and the repository has
no admin owners.

Repositories the shared relationships don't cover (for example internal, private and
archived ones) get business units from the team access the Stats scan job records,
mapped with owners.config the same way (see services/business_units.py).
"""

import json

from sqlalchemy import text
from sqlalchemy.orm import scoped_session

from app.projects.repository_stats.db_models import RepositoryStatsTeamAccess
from app.projects.repository_stats.services.business_units import (
    RepositoryBusinessUnits,
    TeamAccessRow,
    derive_business_units,
    parse_business_unit_config,
)
from app.projects.repository_stats.services.overview_logic import RepositoryTeams, Team
from app.shared.database import db

BUSINESS_UNIT = "BUSINESS_UNIT"
ADMIN_ACCESS = "ADMIN_ACCESS"

_BUSINESS_UNITS_SQL = text(
    """
    SELECT DISTINCT owners.name FROM owners
    JOIN owner_types ON owner_types.id = owners.type_id
    WHERE owner_types.name = :owner_type
    ORDER BY owners.name
    """
)
_REPOSITORY_OWNERS_SQL = text(
    """
    SELECT assets.name, owners.name, owner_types.name, relationships.type
    FROM assets
    JOIN relationships ON relationships.assets_id = assets.id
    JOIN owners ON owners.id = relationships.owners_id
    JOIN owner_types ON owner_types.id = owners.type_id
    ORDER BY assets.name, relationships.id
    """
)

_BUSINESS_UNIT_CONFIGS_SQL = text(
    """
    SELECT owners.name, owners.config FROM owners
    JOIN owner_types ON owner_types.id = owners.type_id
    WHERE owner_types.name = :owner_type
    ORDER BY owners.name
    """
)

# The RepositoryInfo JSON the ownership job stores in assets.data. Only its "access"
# part (team slugs) is used.
_REPOSITORY_TEAMS_SQL = text("SELECT assets.name, assets.data FROM assets")


def authoritative_business_units(rows) -> dict[str, list[str]]:
    """rows: (repository, owner, owner type name, relationship type) tuples."""
    by_repository: dict[str, list[tuple[str, str, str]]] = {}
    for repository, owner, owner_type, relationship_type in rows:
        by_repository.setdefault(repository, []).append(
            (owner, owner_type, relationship_type or "")
        )

    result: dict[str, list[str]] = {}
    for repository, owners in by_repository.items():
        admins = {owner for owner, _, rel in owners if ADMIN_ACCESS in rel}
        business_units = dict.fromkeys(
            owner for owner, owner_type, _ in owners if owner_type == BUSINESS_UNIT
        )
        result[repository] = [
            owner for owner in business_units if owner in admins or not admins
        ]
    return result


def _json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def teams_from_asset_data(data) -> list[str]:
    """Team slugs with admin or any other access, without duplicates. Parent teams are
    not included."""
    data = _json(data)
    access = data.get("access") if isinstance(data, dict) else None
    if not isinstance(access, dict):
        return []
    slugs = [
        *(access.get("teams_with_admin") or []),
        *(access.get("teams") or []),
    ]
    return [slug for slug in dict.fromkeys(slugs) if isinstance(slug, str) and slug]


class OwnershipRepository:
    def __init__(self, db_session: scoped_session | None = None):
        self.db_session = db_session if db_session is not None else db.session
        self.__business_units_by_repository: RepositoryBusinessUnits | None = None
        self.__teams_by_repository: RepositoryTeams | None = None

    def business_unit_names(self) -> list[str]:
        rows = self.db_session.execute(
            _BUSINESS_UNITS_SQL, {"owner_type": BUSINESS_UNIT}
        )
        return [row[0] for row in rows]

    def business_units_by_repository(self) -> RepositoryBusinessUnits:
        """The one business unit source for every Stats page: the shared relationships
        by repository name where they give a business unit, otherwise worked out from
        repository_stats_team_access (by GitHub id) and the name prefixes in
        owners.config."""
        if self.__business_units_by_repository is None:
            rows = self.db_session.execute(_REPOSITORY_OWNERS_SQL)
            by_name = authoritative_business_units(tuple(row) for row in rows)
            configs = [
                parse_business_unit_config(name, _json(config))
                for name, config in self.db_session.execute(
                    _BUSINESS_UNIT_CONFIGS_SQL, {"owner_type": BUSINESS_UNIT}
                )
            ]
            admin, other = derive_business_units(configs, self._team_access_rows())
            self.__business_units_by_repository = RepositoryBusinessUnits(
                by_name={name: units for name, units in by_name.items() if units},
                admin_by_github_id=admin,
                other_by_github_id=other,
                configs=configs,
            )
        return self.__business_units_by_repository

    def _team_access_rows(self) -> list[TeamAccessRow]:
        rows = self.db_session.query(
            RepositoryStatsTeamAccess.org,
            RepositoryStatsTeamAccess.github_id,
            RepositoryStatsTeamAccess.team_slug,
            RepositoryStatsTeamAccess.team_name,
            RepositoryStatsTeamAccess.parent_team_slug,
            RepositoryStatsTeamAccess.permission,
        ).order_by(RepositoryStatsTeamAccess.id)
        return [TeamAccessRow(*row) for row in rows]

    def teams_by_repository(self) -> RepositoryTeams:
        """Teams that can access each repository: the single source of team data for
        the Repository overview.

        Reads repository_stats_team_access, which the Stats scan job fills for every
        repository (any visibility, archived or not), matched by GitHub id. Until that
        table has rows (before the job's first run), falls back to the team slugs in the
        shared ownership data (assets.data, from the Repository Standards ownership job),
        which only covers public, non-archived, non-fork repositories, matched by name.
        """
        if self.__teams_by_repository is None:
            by_github_id = self._teams_by_github_id()
            self.__teams_by_repository = (
                RepositoryTeams(by_github_id=by_github_id)
                if by_github_id
                else RepositoryTeams(by_name=self._teams_by_name_from_assets())
            )
        return self.__teams_by_repository

    def _teams_by_github_id(self) -> dict[int, list[Team]]:
        rows = self.db_session.query(
            RepositoryStatsTeamAccess.github_id,
            RepositoryStatsTeamAccess.team_slug,
            RepositoryStatsTeamAccess.team_name,
        ).order_by(RepositoryStatsTeamAccess.id)
        result: dict[int, list[Team]] = {}
        for github_id, slug, name in rows:
            result.setdefault(github_id, []).append(Team(slug, name or slug))
        return result

    def _teams_by_name_from_assets(self) -> dict[str, list[Team]]:
        rows = self.db_session.execute(_REPOSITORY_TEAMS_SQL)
        return {
            name: [Team(slug, slug) for slug in slugs]
            for name, data in rows
            if (slugs := teams_from_asset_data(data))
        }
