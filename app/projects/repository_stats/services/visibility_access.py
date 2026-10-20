"""GitHub team based access control for Repository Stats.

Access is granted to members of one GitHub team, set with GITHUB_STATS_ACCESS_TEAM as
"org/team-slug" (or just "team-slug" for the ministryofjustice organisation). When it is
unset, everyone who can sign in has access and no GitHub sign-in is needed.

People sign in to this app with Microsoft (Entra ID) through Auth0, which gives us no
GitHub identity. Repository Stats adds a second step: "Continue with GitHub" (a GitHub
OAuth App, see github_sign_in.py) tells us the user's GitHub login. Team membership is
then checked with the Community GitHub App and cached in the session for
ACCESS_RECHECK_SECONDS, after which it is checked again silently with the stored login.

Never log usernames, emails, team names or membership results from this module.
"""

import logging
from collections.abc import Callable, MutableMapping
from enum import Enum
from time import time

from flask import session

from app.projects.repository_stats.clients.github_client import GitHubAppClient
from app.shared.config.app_config import app_config

logger = logging.getLogger(__name__)

DEFAULT_ORG = "ministryofjustice"
# Cached team check results: {"org/team-slug": {"login", "has_access", "checked_at"}}.
SESSION_KEY = "stats_access"
# The GitHub account confirmed with "Continue with GitHub":
# {"login", "auth_sub" (the Auth0 user it was confirmed for), "signed_in_at"}.
GITHUB_SESSION_KEY = "stats_github"
ACCESS_RECHECK_SECONDS = 60 * 60


class GitHubAccessCheckError(Exception):
    """GitHub answered with something other than member (200) or not a member (404)."""


class StatsAccess(Enum):
    ALLOWED = "allowed"
    # Signed in with Microsoft but no GitHub account confirmed yet.
    NEEDS_GITHUB = "needs_github"
    DENIED = "denied"
    # GitHub couldn't be asked; access is denied for now (fail closed).
    UNAVAILABLE = "unavailable"


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


def _auth_subject(session_user: dict | None) -> str | None:
    return ((session_user or {}).get("userinfo") or {}).get("sub") or None


def get_github_login(
    session_user: dict | None, cache: MutableMapping | None = None
) -> str | None:
    """The GitHub login confirmed in this session for the signed-in user, or None.

    A GitHub account confirmed for a different Microsoft user is ignored and removed.
    """
    cache = session if cache is None else cache
    github = cache.get(GITHUB_SESSION_KEY)
    if not isinstance(github, dict) or not github.get("login"):
        return None
    if github.get("auth_sub") != _auth_subject(session_user):
        clear_github_sign_in(cache)
        return None
    return github["login"]


def remember_github_login(
    session_user: dict | None,
    login: str,
    cache: MutableMapping | None = None,
    now: Callable[[], float] = time,
) -> None:
    cache = session if cache is None else cache
    cache[GITHUB_SESSION_KEY] = {
        "login": login,
        "auth_sub": _auth_subject(session_user),
        "signed_in_at": now(),
    }
    # A new GitHub account always gets a fresh team check.
    cache.pop(SESSION_KEY, None)


def clear_github_sign_in(cache: MutableMapping | None = None) -> None:
    """Forget the GitHub part of the session (the Microsoft sign-in is kept)."""
    cache = session if cache is None else cache
    cache.pop(GITHUB_SESSION_KEY, None)
    cache.pop(SESSION_KEY, None)


def check_stats_access(
    session_user: dict | None,
    team: str | None = None,
    cache: MutableMapping | None = None,
    client: GitHubAppClient | None = None,
    now: Callable[[], float] = time,
) -> StatsAccess:
    """team: 'org/team-slug' to check; defaults to GITHUB_STATS_ACCESS_TEAM.

    The team check result is cached in the session and checked again with GitHub once it
    is ACCESS_RECHECK_SECONDS old, so someone removed from the team loses access within
    the hour. A new session has no cached result, so it is always checked. Errors from
    GitHub deny access and are not cached, so the next request tries again.
    """
    required = parse_team(
        team if team is not None else app_config.github.stats_access_team
    )
    if required is None:
        return StatsAccess.ALLOWED

    cache = session if cache is None else cache
    login = get_github_login(session_user, cache)
    if not login:
        return StatsAccess.NEEDS_GITHUB

    team_key = "/".join(required)
    results = cache.get(SESSION_KEY)
    results = dict(results) if isinstance(results, dict) else {}
    cached = results.get(team_key)
    if (
        isinstance(cached, dict)
        and cached.get("login") == login
        and isinstance(cached.get("checked_at"), int | float)
        and 0 <= now() - cached["checked_at"] < ACCESS_RECHECK_SECONDS
    ):
        return StatsAccess.ALLOWED if cached.get("has_access") else StatsAccess.DENIED

    try:
        has_access = is_team_member(login, *required, client=client)
    except GitHubAccessCheckError as error:
        # These messages are ours and only hold status codes, so they are safe to log.
        logger.warning(
            "Repository Stats access check failed; access denied for this request: %s",
            error,
        )
        return StatsAccess.UNAVAILABLE
    except Exception:  # noqa: BLE001 - any failure must deny access, never allow it
        # Includes network errors and a missing or invalid GitHub App key.
        # Deliberately generic: exception text can include request URLs with usernames.
        logger.warning(
            "Repository Stats access check failed; access denied for this request"
        )
        return StatsAccess.UNAVAILABLE

    results[team_key] = {"login": login, "has_access": has_access, "checked_at": now()}
    cache[SESSION_KEY] = results
    return StatsAccess.ALLOWED if has_access else StatsAccess.DENIED
