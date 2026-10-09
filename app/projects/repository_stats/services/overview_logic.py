"""Repository totals by organisation, business unit and team for the Repository
overview page."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import quote

from app.projects.repository_stats.services.business_units import (
    BusinessUnitSource,
    business_units_for,
)
from app.projects.repository_stats.services.visibility_logic import VisibilitySnapshot

UNKNOWN_BUSINESS_UNIT = "Unknown"
NO_TEAM = "No team"


@dataclass
class VisibilityTotals:
    public: int = 0
    internal: int = 0
    private: int = 0
    total: int = 0

    def add(self, visibility: str) -> None:
        self.total += 1
        if visibility in ("public", "internal", "private"):
            setattr(self, visibility, getattr(self, visibility) + 1)


@dataclass
class OverviewRow:
    name: str
    totals: VisibilityTotals = field(default_factory=VisibilityTotals)
    children: list["OverviewRow"] = field(default_factory=list)
    # The ?open= value that expands this row: "<org>" or "<org>/<business unit>".
    key: str | None = None
    # GitHub team page, for team rows only.
    url: str | None = None


@dataclass(frozen=True)
class Team:
    slug: str
    name: str


@dataclass(frozen=True)
class RepositoryTeams:
    """Teams that can access each repository, by GitHub id (collected by the Stats
    scan job) or, before its first run, by repository name (the shared ownership
    data)."""

    by_github_id: Mapping[int, Sequence[Team]] = field(default_factory=dict)
    by_name: Mapping[str, Sequence[Team]] = field(default_factory=dict)

    def for_repository(self, github_id: int, name: str) -> Sequence[Team]:
        return self.by_github_id.get(github_id) or self.by_name.get(name) or ()


@dataclass
class Overview:
    all_organisations: OverviewRow
    organisations: list[OverviewRow]


def team_url(org: str, slug: str) -> str:
    return f"https://github.com/orgs/{quote(org, safe='')}/teams/{quote(slug, safe='')}"


def business_unit_key(org: str, business_unit: str) -> str:
    return f"{org}/{business_unit}"


def _sorted(rows: Iterable[OverviewRow], last: str) -> list[OverviewRow]:
    return sorted(rows, key=lambda row: (row.name == last, row.name.lower()))


def build_overview(
    snapshots: Iterable[VisibilitySnapshot],
    business_units: BusinessUnitSource,
    repository_teams: RepositoryTeams | None = None,
    organisation_names: Mapping[str, str] | None = None,
) -> Overview:
    """Count the latest snapshot by organisation, then business unit, then team.

    A repository owned by several business units counts under each one, and a repository
    several teams can access counts under each of those teams. Repositories with no
    business unit count under "Unknown"; those with no team count under "No team".
    Organisations show their display name (organisation_names, by login) if known, and
    are keyed by login.
    """
    organisation_names = organisation_names or {}
    repository_teams = repository_teams or RepositoryTeams()
    all_organisations = OverviewRow("All organisations")
    organisations: dict[str, OverviewRow] = {}
    unit_rows: dict[str, dict[str, OverviewRow]] = {}
    teams: dict[tuple[str, str], dict[str, OverviewRow]] = {}

    for snapshot in snapshots:
        visibility = snapshot.visibility
        all_organisations.totals.add(visibility)
        org = organisations.setdefault(
            snapshot.org,
            OverviewRow(
                organisation_names.get(snapshot.org) or snapshot.org, key=snapshot.org
            ),
        )
        org.totals.add(visibility)

        owners = business_units_for(business_units, snapshot.github_id, snapshot.name)
        repo_teams = list(
            {
                team.slug: team
                for team in repository_teams.for_repository(
                    snapshot.github_id, snapshot.name
                )
            }.values()
        )
        by_name = unit_rows.setdefault(snapshot.org, {})
        for owner in owners or (UNKNOWN_BUSINESS_UNIT,):
            business_unit = by_name.setdefault(
                owner,
                OverviewRow(owner, key=business_unit_key(snapshot.org, owner)),
            )
            business_unit.totals.add(visibility)
            team_rows = teams.setdefault((snapshot.org, owner), {})
            for team in repo_teams:
                team_rows.setdefault(
                    team.slug,
                    OverviewRow(team.name, url=team_url(snapshot.org, team.slug)),
                ).totals.add(visibility)
            if not repo_teams:
                team_rows.setdefault(NO_TEAM, OverviewRow(NO_TEAM)).totals.add(
                    visibility
                )

    for org_name, org in organisations.items():
        org.children = _sorted(
            unit_rows.get(org_name, {}).values(), UNKNOWN_BUSINESS_UNIT
        )
        for business_unit in org.children:
            business_unit.children = _sorted(
                teams.get((org_name, business_unit.name), {}).values(), NO_TEAM
            )

    return Overview(
        all_organisations=all_organisations,
        organisations=sorted(organisations.values(), key=lambda r: r.name.lower()),
    )
