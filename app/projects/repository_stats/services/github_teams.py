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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock, local
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
MAX_TEAM_ACCESS_WORKERS = 3
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
        # The coordinated transport already retries connection failures and 5xxs.
        self.transport_retries_failures = (
            getattr(client, "request_coordinator", None) is not None
        )

    def get(self, path: str):
        for attempt in range(1, self.attempts + 1):
            last = attempt == self.attempts
            try:
                response = self.client.get(path)
            except (requests.Timeout, requests.ConnectionError) as error:
                if last or self.transport_retries_failures:
                    raise
                reason = type(error).__name__
            else:
                if (
                    response.status_code < 500
                    or last
                    or self.transport_retries_failures
                ):
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
    workers: int = 1,
    client_for_worker: Callable[[], GitHubGetter] | None = None,
) -> list[TeamAccessRecord]:
    """One record per team per repository it can access.

    Each call is retried (see RetryingGetter). A team whose repository list returns 404
    (e.g. renamed or deleted during the scan) is skipped with a warning and the other
    teams are still returned. Any other failure raises GitHubInventoryError, or the
    network error, so the caller can keep the previous data rather than store a partial
    set.
    """
    if not 1 <= workers <= MAX_TEAM_ACCESS_WORKERS:
        raise ValueError(
            f"Team access workers must be between 1 and {MAX_TEAM_ACCESS_WORKERS}"
        )
    client = RetryingGetter(client, sleep=sleep)
    records: dict[tuple[int, str], TeamAccessRecord] = {}
    teams = get_all_pages(client, f"/orgs/{org}/teams?per_page={PER_PAGE}", "team")
    for team in teams:
        if not team.get("slug"):
            raise GitHubInventoryError("GitHub API returned a team without a slug")

    def fetch_team(team: dict, team_client: GitHubGetter) -> list[TeamAccessRecord]:
        slug = team.get("slug")
        parent = (team.get("parent") or {}).get("slug")
        path = f"/orgs/{org}/teams/{quote(slug, safe='')}/repos?per_page={PER_PAGE}"
        try:
            getter = (
                team_client
                if isinstance(team_client, RetryingGetter)
                else RetryingGetter(team_client, sleep=sleep)
            )
            repositories = get_all_pages(getter, path, "team repository")
        except GitHubInventoryError as error:
            if error.status_code != 404:
                raise
            logger.warning(
                "Skipping team %s in %s: GitHub returned 404 for its repositories "
                "(renamed or deleted during the scan?)",
                slug,
                org,
            )
            return []
        team_records = []
        for repository in repositories:
            record = TeamAccessRecord(
                org=org,
                github_id=int(repository["id"]),
                team_slug=slug,
                team_name=team.get("name") or slug,
                parent_team_slug=parent,
                permission=team_permission(repository),
            )
            team_records.append(record)
        return team_records

    if workers == 1 or client_for_worker is None or len(teams) < 2:
        for team in teams:
            for record in fetch_team(team, client):
                records[(record.github_id, record.team_slug)] = record
        return list(records.values())

    worker_state = local()
    worker_clients = []
    registry_lock = Lock()

    def fetch_with_worker(team: dict) -> list[TeamAccessRecord]:
        if not hasattr(worker_state, "client"):
            worker_state.client = client_for_worker()
            with registry_lock:
                worker_clients.append(worker_state.client)
        return fetch_team(team, worker_state.client)

    try:
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="repo-stats-teams"
        ) as executor:
            futures = {
                executor.submit(fetch_with_worker, team): index
                for index, team in enumerate(teams)
            }
            by_index = {}
            try:
                for future in as_completed(futures):
                    by_index[futures[future]] = future.result()
            except Exception:
                for future in futures:
                    future.cancel()
                raise
        for index in range(len(teams)):
            for record in by_index[index]:
                records[(record.github_id, record.team_slug)] = record
    finally:
        for worker_client in worker_clients:
            close = getattr(worker_client, "close", None)
            if close:
                close()
    return list(records.values())
