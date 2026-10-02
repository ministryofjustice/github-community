"""GitHub team based access control for Repository Stats.

Access is granted to members of one GitHub team, set with GITHUB_STATS_ACCESS_TEAM as
"org/team-slug" (or just "team-slug" for the ministryofjustice organisation). When it is
unset, everyone who can sign in has access.

Working out the signed-in user's GitHub login:
- People sign in to this app with Microsoft (Entra ID) through Auth0, so the ID token
  has no GitHub identity. The team's organisation enforces SAML single sign-on, and
  GitHub records each member's SAML identity (their Entra email and UPN) against their
  GitHub login. We match the ID token's verified work email to those SAML identities,
  read through the GitHub App with GraphQL (organization.samlIdentityProvider
  .externalIdentities). The SAML NameID can't be used: it comes from a different Auth0
  tenant and is a pairwise id, so it never equals this app's "sub".
- An Auth0 GitHub social login ("sub" is "github|<id>") is still supported.
- A free-text nickname is never trusted on its own.

Never log usernames, emails, team names or membership results from this module.
"""

import logging
import re
import threading
from collections.abc import Callable, MutableMapping
from datetime import UTC, datetime
from time import monotonic

from flask import session

from app.projects.repository_stats.clients.github_client import GitHubAppClient
from app.shared.config.app_config import app_config

logger = logging.getLogger(__name__)

DEFAULT_ORG = "ministryofjustice"
SESSION_KEY = "stats_access"
GITHUB_SUB_PATTERN = re.compile(r"^github\|(\d+)$")
# Work email domains seen in the ministryofjustice SAML identities. Only emails on these
# domains are matched to a GitHub login.
ALLOWED_EMAIL_DOMAINS = frozenset(
    {
        "justice.gov.uk",
        "digital.justice.gov.uk",
        "publicguardian.gov.uk",
        "cica.gov.uk",
    }
)
UPN_ATTRIBUTE = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn"
# The email -> login map for an organisation is shared by everyone signing in, so the
# whole organisation is paged through at most once per this many seconds per process.
SAML_EMAIL_MAP_TTL_SECONDS = 15 * 60
SAML_IDENTITIES_QUERY = """
query($org: String!, $cursor: String) {
  organization(login: $org) {
    samlIdentityProvider {
      externalIdentities(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          samlIdentity { nameId username emails { value } attributes { name value } }
          user { login }
        }
      }
    }
  }
}
"""


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


def _normalise_email(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    local, at, domain = value.rpartition("@")
    if not at or not local or not domain:
        return None
    return value


def fetch_saml_email_map(org: str, client: GitHubAppClient | None = None) -> dict:
    """Every SAML identity email (and UPN) in the organisation -> GitHub login.

    An email linked to more than one GitHub login maps to None, so it never grants
    access. Docs: https://docs.github.com/en/graphql/reference/objects#externalidentity
    """
    client = client or get_github_client()
    logins_by_email: dict[str, set[str]] = {}
    cursor = None
    while True:
        response = client.graphql(SAML_IDENTITIES_QUERY, {"org": org, "cursor": cursor})
        if response.status_code != 200:
            raise GitHubAccessCheckError(
                f"GitHub SAML identity lookup failed with status {response.status_code}"
            )
        body = response.json()
        if not isinstance(body, dict) or body.get("errors"):
            error_types = sorted(
                {
                    str(error.get("type") or "unknown")
                    for error in (body or {}).get("errors") or []
                    if isinstance(error, dict)
                }
            )
            raise GitHubAccessCheckError(
                f"GitHub SAML identity lookup returned errors: {error_types}"
            )
        provider = ((body.get("data") or {}).get("organization") or {}).get(
            "samlIdentityProvider"
        )
        if not provider:
            raise GitHubAccessCheckError(
                "GitHub SAML identity provider is not visible to the GitHub App"
            )
        identities = provider.get("externalIdentities") or {}
        for node in identities.get("nodes") or []:
            login = ((node or {}).get("user") or {}).get("login")
            if not login:
                continue
            saml = node.get("samlIdentity") or {}
            candidates = [email.get("value") for email in saml.get("emails") or []]
            candidates += [saml.get("username"), saml.get("nameId")]
            candidates += [
                attribute.get("value")
                for attribute in saml.get("attributes") or []
                if attribute.get("name") == UPN_ATTRIBUTE
            ]
            for candidate in candidates:
                email = _normalise_email(candidate)
                if email:
                    logins_by_email.setdefault(email, set()).add(login.lower())
        page_info = identities.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            raise GitHubAccessCheckError("GitHub SAML identity paging stopped early")
    return {
        email: next(iter(logins)) if len(logins) == 1 else None
        for email, logins in logins_by_email.items()
    }


_saml_email_maps: dict[str, tuple[float, dict]] = {}
_saml_email_maps_lock = threading.Lock()


def clear_saml_email_map_cache() -> None:
    with _saml_email_maps_lock:
        _saml_email_maps.clear()


def get_username_by_email(
    email: str, org: str, client: GitHubAppClient | None = None
) -> str | None:
    """The GitHub login whose SAML identity in org has this email, or None.

    The org-wide map is cached in this process for SAML_EMAIL_MAP_TTL_SECONDS. A failed
    fetch raises and caches nothing.
    """
    org_key = org.lower()
    with _saml_email_maps_lock:
        cached = _saml_email_maps.get(org_key)
        if cached is None or monotonic() - cached[0] >= SAML_EMAIL_MAP_TTL_SECONDS:
            cached = (monotonic(), fetch_saml_email_map(org, client))
            _saml_email_maps[org_key] = cached
    return cached[1].get(email.lower())


def verified_work_email(userinfo: dict) -> str | None:
    """The ID token's email, only if Auth0 says it is verified and it's an MoJ domain."""
    verified = userinfo.get("email_verified")
    if not (verified is True or (isinstance(verified, str) and verified == "true")):
        return None
    email = _normalise_email(userinfo.get("email"))
    if not email or email.rpartition("@")[2] not in ALLOWED_EMAIL_DOMAINS:
        return None
    return email


def resolve_github_username(
    session_user: dict | None,
    lookup_by_id: Callable[[str], str | None] = get_username_by_id,
    lookup_by_email: Callable[[str], str | None] | None = None,
) -> str | None:
    """The GitHub username of the signed-in user, or None if it can't be worked out.

    session["user"] is the Auth0 token response; "userinfo" holds the ID token claims.

    GitHub social connection: "sub" is "github|<numeric GitHub user id>" and "nickname"
    is normally the GitHub login. If "nickname" is missing we look the login up from the
    numeric id.

    Any other connection (Microsoft / Entra ID in practice): the verified MoJ work email
    is looked up with lookup_by_email (the organisation's SAML identities). "nickname" is
    ignored here: it is the email local part for Microsoft and user-chosen for some other
    connections, so it could match someone else's GitHub login.
    """
    userinfo = (session_user or {}).get("userinfo") or {}
    match = GITHUB_SUB_PATTERN.match(userinfo.get("sub") or "")
    if match:
        nickname = (userinfo.get("nickname") or "").strip()
        if nickname:
            return nickname
        return lookup_by_id(match.group(1))
    if lookup_by_email is None:
        return None
    email = verified_work_email(userinfo)
    if not email:
        return None
    return lookup_by_email(email)


def user_has_stats_access(
    session_user: dict | None,
    team: str | None = None,
    cache: MutableMapping | None = None,
    client: GitHubAppClient | None = None,
) -> bool:
    """team: 'org/team-slug' to check; defaults to GITHUB_STATS_ACCESS_TEAM.

    The result is cached in the login session, so GitHub is only asked once per login.
    Errors from GitHub deny access and are not cached, so the next request tries again.
    A user whose GitHub login can't be worked out is denied and not cached either, so
    someone who links their account later doesn't have to sign out and in again.
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
            session_user,
            lambda github_id: get_username_by_id(github_id, client),
            lambda email: get_username_by_email(email, required[0], client),
        )
        has_access = bool(username) and is_team_member(
            username, *required, client=client
        )
    except GitHubAccessCheckError as error:
        # These messages are ours and only hold status codes or GraphQL error types, so
        # they are safe to log and show a missing GitHub App permission.
        logger.warning(
            "Repository Stats access check failed; access denied for this request: %s",
            error,
        )
        return False
    except Exception:  # noqa: BLE001 - any failure must deny access, never allow it
        # Includes network errors and a missing or invalid GitHub App key.
        # Deliberately generic: exception text can include request URLs with usernames.
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
