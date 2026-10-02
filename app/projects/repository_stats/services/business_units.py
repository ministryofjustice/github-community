"""Business units for every repository: the one business unit source for all Repository
Stats pages.

Two inputs, read-only:
- the shared ownership relationships (assets, from the Repository Standards ownership
  job), matched by repository name. Where these give a business unit, they win.
- the team access the Stats scan job records for every repository
  (repository_stats_team_access), matched by GitHub id, mapped to business units with
  the shared owners.config (teams and name prefix per business unit).

The team rule matches map_github_repositories_to_owners in Repository Standards: a
business unit has admin access when one of its teams (or a parent of one) has admin
access, and other access when one of its teams (or a parent) has any access or the
repository name starts with its prefix. If any business unit has admin access, only those
count; otherwise all with other access count.

This module must not import Flask or SQLAlchemy.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

ADMIN_PERMISSION = "admin"


@dataclass(frozen=True)
class BusinessUnitConfig:
    name: str
    # Team slugs or display names, compared without case.
    teams: tuple[str, ...] = ()
    prefix: str = ""


@dataclass(frozen=True)
class TeamAccessRow:
    org: str
    github_id: int
    team_slug: str
    team_name: str
    parent_team_slug: str | None
    permission: str


@dataclass(frozen=True)
class RepositoryBusinessUnits:
    by_name: Mapping[str, Sequence[str]] = field(default_factory=dict)
    admin_by_github_id: Mapping[int, Sequence[str]] = field(default_factory=dict)
    other_by_github_id: Mapping[int, Sequence[str]] = field(default_factory=dict)
    configs: Sequence[BusinessUnitConfig] = ()

    def for_repository(self, github_id: int, name: str) -> tuple[str, ...]:
        if owners := self.by_name.get(name):
            return tuple(dict.fromkeys(owners))
        admin = self.admin_by_github_id.get(github_id, ())
        if admin:
            return tuple(dict.fromkeys(admin))
        other = [
            *self.other_by_github_id.get(github_id, ()),
            *(c.name for c in self.configs if c.prefix and name.startswith(c.prefix)),
        ]
        return tuple(dict.fromkeys(other))


BusinessUnitSource = RepositoryBusinessUnits | Mapping[str, Sequence[str]]


def business_units_for(
    source: BusinessUnitSource, github_id: int, name: str
) -> tuple[str, ...]:
    """Business units of one repository from either the full source or a plain mapping
    of repository name to business units."""
    if isinstance(source, RepositoryBusinessUnits):
        return source.for_repository(github_id, name)
    return tuple(dict.fromkeys(source.get(name, ())))


def parse_business_unit_config(name: str, config) -> BusinessUnitConfig:
    """owners.config JSON ({"name", "teams", "prefix"}); missing parts are empty."""
    config = config if isinstance(config, dict) else {}
    teams = config.get("teams")
    prefix = config.get("prefix")
    return BusinessUnitConfig(
        name=name,
        teams=tuple(t for t in teams if isinstance(t, str) and t.strip())
        if isinstance(teams, list)
        else (),
        prefix=prefix if isinstance(prefix, str) else "",
    )


def _team_keys(slug: str, name: str | None) -> set[str]:
    return {value.strip().lower() for value in (slug, name) if value}


def derive_business_units(
    configs: Iterable[BusinessUnitConfig], rows: Iterable[TeamAccessRow]
) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    """Business units with admin access and with other access, by GitHub id, from team
    access. Parent teams are followed through the parent slugs recorded for the org's
    teams (only teams that can access at least one repository are recorded, so a chain
    stops at a parent with no access of its own)."""
    configs = list(configs)
    rows = list(rows)
    team_names: dict[tuple[str, str], str] = {}
    parents: dict[tuple[str, str], str] = {}
    for row in rows:
        team_names[(row.org, row.team_slug)] = row.team_name
        if row.parent_team_slug:
            parents[(row.org, row.team_slug)] = row.parent_team_slug

    def lineage(org: str, slug: str) -> set[str]:
        keys: set[str] = set()
        seen: set[str] = set()
        current: str | None = slug
        while current and current not in seen:
            seen.add(current)
            keys |= _team_keys(current, team_names.get((org, current)))
            current = parents.get((org, current))
        return keys

    config_teams = [
        (config.name, {team.strip().lower() for team in config.teams})
        for config in configs
    ]
    admin: dict[int, list[str]] = {}
    other: dict[int, list[str]] = {}
    for row in rows:
        keys = lineage(row.org, row.team_slug)
        for name, teams in config_teams:
            if not teams & keys:
                continue
            target = admin if row.permission == ADMIN_PERMISSION else other
            owners = target.setdefault(row.github_id, [])
            if name not in owners:
                owners.append(name)
    return admin, other
