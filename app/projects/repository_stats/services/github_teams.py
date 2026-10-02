"""Which teams can access each repository in a GitHub organisation.

Lists the organisation's teams, then each team's repositories, so the number of API
calls grows with the number of teams rather than the number of repositories. Needs the
GitHub App's organisation "Members: read" and repository "Metadata: read" permissions.
"""

from dataclasses import dataclass
from urllib.parse import quote

from app.projects.repository_stats.services.github_inventory import (
    PER_PAGE,
    GitHubGetter,
    GitHubInventoryError,
    get_all_pages,
)

# Highest first, for responses without role_name.
_PERMISSIONS = ("admin", "maintain", "push", "triage", "pull")
_ROLE_NAMES = {"push": "write", "pull": "read"}


@dataclass(frozen=True)
class TeamAccessRecord:
    org: str
    github_id: int
    team_slug: str
    team_name: str
    parent_team_slug: str | None
    permission: str


def team_permission(repository: dict) -> str:
    """GitHub's role name for the team on this repository, e.g. "admin" or "write"."""
    if role_name := repository.get("role_name"):
        return str(role_name)
    permissions = repository.get("permissions") or {}
    for permission in _PERMISSIONS:
        if permissions.get(permission):
            return _ROLE_NAMES.get(permission, permission)
    return "unknown"


def fetch_org_team_access(client: GitHubGetter, org: str) -> list[TeamAccessRecord]:
    """One record per team per repository it can access.

    Raises GitHubInventoryError if any list can't be fetched in full, so the caller can
    keep the previous data rather than store a partial set.
    """
    records: dict[tuple[int, str], TeamAccessRecord] = {}
    teams = get_all_pages(client, f"/orgs/{org}/teams?per_page={PER_PAGE}", "team")
    for team in teams:
        slug = team.get("slug")
        if not slug:
            raise GitHubInventoryError("GitHub API returned a team without a slug")
        parent = (team.get("parent") or {}).get("slug")
        path = f"/orgs/{org}/teams/{quote(slug, safe='')}/repos?per_page={PER_PAGE}"
        for repository in get_all_pages(client, path, "team repository"):
            record = TeamAccessRecord(
                org=org,
                github_id=int(repository["id"]),
                team_slug=slug,
                team_name=team.get("name") or slug,
                parent_team_slug=parent,
                permission=team_permission(repository),
            )
            records[(record.github_id, slug)] = record
    return list(records.values())
