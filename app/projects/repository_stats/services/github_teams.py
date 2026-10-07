"""Which teams can access each repository in a GitHub organisation.

Lists the organisation's teams, then each team's repositories, so the number of API
calls grows with the number of teams rather than the number of repositories. Needs the
GitHub App's organisation "Members: read" and repository "Metadata: read" permissions.

Every call is retried a few times on timeouts, connection errors and 5xx responses, so
one slow call doesn't lose the team data for the whole run.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

import requests

from app.projects.repository_stats.services.github_inventory import (
    PER_PAGE,
    GitHubGetter,
    GitHubInventoryError,
    get_all_pages,
)

# Highest first, for responses without role_name.
_PERMISSIONS = ("admin", "maintain", "push", "triage", "pull")
_ROLE_NAMES = {"push": "write", "pull": "read"}

MAX_ATTEMPTS = 3
# Seconds to wait before the 2nd and 3rd attempts.
RETRY_BACKOFF_SECONDS = (2, 5)

logger = logging.getLogger(__name__)


class RetryingGetter:
    """Wraps a GitHub client; retries each GET on timeouts, connection errors and 5xx.

    After the last attempt the error is raised (or the 5xx response returned) as usual.
    """

    def __init__(
        self,
        client: GitHubGetter,
        attempts: int = MAX_ATTEMPTS,
        backoff: tuple[float, ...] = RETRY_BACKOFF_SECONDS,
        sleep: Callable[[float], None] | None = None,
    ):
        self.client = client
        self.attempts = max(1, attempts)
        self.backoff = backoff
        self.sleep = sleep or time.sleep

    def get(self, path: str):
        for attempt in range(1, self.attempts + 1):
            last = attempt == self.attempts
            try:
                response = self.client.get(path)
            except (requests.Timeout, requests.ConnectionError) as error:
                if last:
                    raise
                reason = type(error).__name__
            else:
                if response.status_code < 500 or last:
                    return response
                reason = f"status {response.status_code}"
            delay = (
                self.backoff[min(attempt, len(self.backoff)) - 1] if self.backoff else 0
            )
            # No path in the log: team slugs are fine but keep job logs short.
            logger.warning(
                "GitHub team call failed (%s); retrying in %ss (attempt %s of %s)",
                reason,
                delay,
                attempt + 1,
                self.attempts,
            )
            self.sleep(delay)
        raise AssertionError("unreachable")


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


def fetch_org_team_access(
    client: GitHubGetter,
    org: str,
    sleep: Callable[[float], None] | None = None,
) -> list[TeamAccessRecord]:
    """One record per team per repository it can access.

    Each call is retried (see RetryingGetter). A team whose repository list returns 404
    (e.g. renamed or deleted during the scan) is skipped with a warning and the other
    teams are still returned. Any other failure raises GitHubInventoryError, or the
    network error, so the caller can keep the previous data rather than store a partial
    set.
    """
    client = RetryingGetter(client, sleep=sleep)
    records: dict[tuple[int, str], TeamAccessRecord] = {}
    teams = get_all_pages(client, f"/orgs/{org}/teams?per_page={PER_PAGE}", "team")
    for team in teams:
        slug = team.get("slug")
        if not slug:
            raise GitHubInventoryError("GitHub API returned a team without a slug")
        parent = (team.get("parent") or {}).get("slug")
        path = f"/orgs/{org}/teams/{quote(slug, safe='')}/repos?per_page={PER_PAGE}"
        try:
            repositories = get_all_pages(client, path, "team repository")
        except GitHubInventoryError as error:
            if error.status_code != 404:
                raise
            logger.warning(
                "Skipping team %s in %s: GitHub returned 404 for its repositories "
                "(renamed or deleted during the scan?)",
                slug,
                org,
            )
            continue
        for repository in repositories:
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
