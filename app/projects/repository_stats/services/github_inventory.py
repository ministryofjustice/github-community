"""List every repository in a GitHub organisation for the visibility job."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

PER_PAGE = 100
# 1,000 pages of 100 is far beyond any MoJ organisation; it only stops a broken "next" loop.
MAX_PAGES = 1000


class GitHubInventoryError(Exception):
    """GitHub didn't return a complete repository list, so the run must not write anything."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        # The HTTP status GitHub returned, when the error came from a response.
        self.status_code = status_code


class GitHubGetter(Protocol):
    def get(self, path: str): ...


@dataclass(frozen=True)
class RepositoryRecord:
    github_id: int
    org: str
    name: str
    visibility: str
    archived: bool
    fork: bool
    created_at: datetime | None
    pushed_at: datetime | None


def parse_github_datetime(value: str | None) -> datetime | None:
    """GitHub's "2023-05-06T12:00:00Z" as a naive UTC datetime, like the existing columns."""
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(UTC).replace(tzinfo=None)


def to_record(org: str, data: dict) -> RepositoryRecord:
    visibility = data.get("visibility") or (
        "private" if data.get("private") else "public"
    )
    return RepositoryRecord(
        github_id=int(data["id"]),
        org=org,
        name=data["name"],
        visibility=visibility,
        archived=bool(data.get("archived")),
        fork=bool(data.get("fork")),
        created_at=parse_github_datetime(data.get("created_at")),
        pushed_at=parse_github_datetime(data.get("pushed_at")),
    )


def _raise_for_status(response) -> None:
    if response.status_code == 200:
        return
    headers = getattr(response, "headers", None) or {}
    if response.status_code in (403, 429) and (
        headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers
    ):
        reset = (
            headers.get("x-ratelimit-reset") or headers.get("retry-after") or "unknown"
        )
        raise GitHubInventoryError(f"GitHub API rate limit reached (reset: {reset})")
    raise GitHubInventoryError(
        f"GitHub API returned status {response.status_code}",
        status_code=response.status_code,
    )


def get_all_pages(client: GitHubGetter, path: str, what: str) -> list[dict]:
    """Every item from a paginated list endpoint.

    Follows the Link "next" header until the last page. Raises GitHubInventoryError on
    any non-200 response or unexpected body, so callers never work from a partial list.
    """
    items: list[dict] = []
    for _ in range(MAX_PAGES):
        response = client.get(path)
        _raise_for_status(response)
        body = response.json()
        if not isinstance(body, list):
            raise GitHubInventoryError(f"GitHub API returned an unexpected {what} list")
        items.extend(body)
        next_link = (getattr(response, "links", None) or {}).get("next", {}).get("url")
        if not next_link:
            return items
        path = next_link
    raise GitHubInventoryError("GitHub API pagination did not finish")


def fetch_org_repositories(client: GitHubGetter, org: str) -> list[RepositoryRecord]:
    """Every repository in the organisation (all types, including archived and forks)."""
    records: dict[int, RepositoryRecord] = {}
    for data in get_all_pages(
        client, f"/orgs/{org}/repos?type=all&per_page={PER_PAGE}", "repository"
    ):
        record = to_record(org, data)
        records[record.github_id] = record
    return list(records.values())


@dataclass(frozen=True)
class OrganisationProfile:
    login: str
    # GitHub's display name for the organisation, or None if it has none.
    display_name: str | None


def fetch_org_profile(client: GitHubGetter, org: str) -> OrganisationProfile:
    """The organisation's display name (GET /orgs/{org})."""
    response = client.get(f"/orgs/{org}")
    _raise_for_status(response)
    body = response.json()
    if not isinstance(body, dict):
        raise GitHubInventoryError("GitHub API returned an unexpected organisation")
    name = body.get("name")
    name = name.strip() if isinstance(name, str) else ""
    return OrganisationProfile(org, name or None)


class CountingGetter:
    """Wraps a GitHub client and counts its API calls, for the job log."""

    def __init__(self, client: GitHubGetter):
        self.client = client
        self.calls = 0

    def get(self, path: str):
        self.calls += 1
        return self.client.get(path)
