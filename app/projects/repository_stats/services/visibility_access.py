"""GitHub team based access control for Repository Stats.

Access is granted to members of one GitHub team, set with GITHUB_STATS_ACCESS_TEAM as
"org/team-slug" (or just "team-slug" for the ministryofjustice organisation). When it is
unset, everyone who can sign in has access.

Never log usernames, team names or membership results from this module.
"""

import logging
import re
from collections.abc import Callable, MutableMapping
from datetime import UTC, datetime

from flask import session

from app.projects.repository_stats.clients.github_client import GitHubAppClient
from app.shared.config.app_config import app_config

logger = logging.getLogger(__name__)

DEFAULT_ORG = "ministryofjustice"
SESSION_KEY = "stats_access"
GITHUB_SUB_PATTERN = re.compile(r"^github\|(\d+)$")


class GitHubAccessCheckError(Exception):
    """GitHub answered with something other than member (200) or not a member (404)."""


def parse_team(value: str | None) -> tuple[str, str] | None:
    """'org/team-slug' or 'team-slug' -> (org, team_slug). None when unset or blank."""
    value = (value or "").strip().strip("/")
    if not value:
        return None
    org, _, team_slug = value.rpartition("/")
    return (org or DEFAULT_ORG), team_slug


def get_github_client() -> GitHubAppClient:
    return GitHubAppClient(
        app_config.github.app.client_id,
        app_config.github.app.private_key,
        app_config.github.app.installation_id,
    )


def is_team_member(
    github_username: str,
    org: str,
    team_slug: str,
    client: GitHubAppClient | None = None,
) -> bool:
    """Docs: https://docs.github.com/en/rest/teams/members#get-team-membership-for-a-user"""
    client = client or get_github_client()
    response = client.get(
        f"/orgs/{org}/teams/{team_slug}/memberships/{github_username}"
    )
    if response.status_code == 200:
        # Pending invitations also return 200; only an active membership counts.
        # Fail closed: a non-dict body or a missing "state" must not grant access.
        body = response.json()
        return isinstance(body, dict) and body.get("state") == "active"
    if response.status_code == 404:
        return False
    raise GitHubAccessCheckError(
        f"GitHub team membership check failed with status {response.status_code}"
    )


def get_username_by_id(
    github_id: str, client: GitHubAppClient | None = None
) -> str | None:
    """Docs: https://docs.github.com/en/rest/users/users#get-a-user-using-their-id"""
    client = client or get_github_client()
    response = client.get(f"/user/{github_id}")
    if response.status_code == 200:
        return response.json().get("login") or None
    if response.status_code == 404:
        return None
    raise GitHubAccessCheckError(
        f"GitHub user lookup failed with status {response.status_code}"
    )


def resolve_github_username(
    session_user: dict | None,
    lookup_by_id: Callable[[str], str | None] = get_username_by_id,
) -> str | None:
    """The GitHub username of the signed-in user, or None if it can't be worked out.

    session["user"] is the Auth0 token response; "userinfo" holds the ID token claims.
    For the Auth0 GitHub social connection, "nickname" is normally the GitHub login and
    "sub" is "github|<numeric GitHub user id>". We don't control what Auth0 puts in the
    token (Auth0 Actions or connection settings can change or drop "nickname"), so if
    "nickname" is missing we fall back to the numeric id in "sub" and look the login up
    through the GitHub API. Any other kind of "sub" (not a GitHub login) gives None, even
    with a "nickname": other Auth0 connections let users choose their nickname, so it
    could match someone else's GitHub login.
    """
    userinfo = (session_user or {}).get("userinfo") or {}
    match = GITHUB_SUB_PATTERN.match(userinfo.get("sub") or "")
    if not match:
        return None
    nickname = (userinfo.get("nickname") or "").strip()
    if nickname:
        return nickname
    return lookup_by_id(match.group(1))


def user_has_stats_access(
    session_user: dict | None,
    team: str | None = None,
    cache: MutableMapping | None = None,
    client: GitHubAppClient | None = None,
) -> bool:
    """team: 'org/team-slug' to check; defaults to GITHUB_STATS_ACCESS_TEAM.

    The result is cached in the login session, so GitHub is only asked once per login.
    Errors from GitHub deny access and are not cached, so the next request tries again.
    """
    required = parse_team(
        team if team is not None else app_config.github.stats_access_team
    )
    if required is None:
        return True

    cache = session if cache is None else cache
    team_key = "/".join(required)
    subject = ((session_user or {}).get("userinfo") or {}).get("sub")
    cached = cache.get(SESSION_KEY)
    if (
        cached
        and subject
        and cached.get("sub") == subject
        and cached.get("team") == team_key
    ):
        return bool(cached.get("has_access"))

    try:
        username = resolve_github_username(
            session_user, lambda github_id: get_username_by_id(github_id, client)
        )
        has_access = bool(username) and is_team_member(
            username, *required, client=client
        )
    except Exception:  # noqa: BLE001 - any failure must deny access, never allow it
        # Includes network errors and a missing or invalid GitHub App key.
        # Deliberately generic: no username, team or response details are logged.
        logger.debug(
            "Repository Stats access check failed; access denied for this request"
        )
        return False

    if username:
        cache[SESSION_KEY] = {
            "sub": subject,
            "username": username,
            "team": team_key,
            "has_access": has_access,
            "checked_at": datetime.now(UTC).isoformat(),
        }
    return has_access
