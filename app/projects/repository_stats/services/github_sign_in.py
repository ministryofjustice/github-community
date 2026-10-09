"""The "Continue with GitHub" step for Repository Stats.

A plain GitHub OAuth App (GITHUB_STATS_OAUTH_CLIENT_ID / _SECRET) with no scopes: we only
read the signed-in user's login from GET /user. The access token is used for that one
call and then thrown away; it is never stored or logged.

Docs: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
"""

import hmac
import re
import secrets
from collections.abc import MutableMapping
from urllib.parse import urlencode, urlsplit

import requests

from app.shared.config.app_config import app_config

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
REQUEST_TIMEOUT_SECONDS = 10

STATE_SESSION_KEY = "stats_github_oauth_state"
NEXT_SESSION_KEY = "stats_github_next"
STATS_PATH_PREFIX = "/repository-stats/"
# GitHub logins: letters, digits and single hyphens, up to 39 characters.
GITHUB_LOGIN_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


class GitHubSignInError(Exception):
    """GitHub didn't confirm the account (bad code, unexpected answer). Safe to log."""


class GitHubUnavailableError(GitHubSignInError):
    """GitHub couldn't be reached or had a server error. Safe to log."""


def is_configured() -> bool:
    oauth = app_config.github.stats_oauth
    return bool(oauth.client_id and oauth.client_secret)


def authorize_url(redirect_uri: str, cache: MutableMapping) -> str:
    """GitHub's sign-in page URL, with a new one-time state saved in the session."""
    state = secrets.token_urlsafe(32)
    cache[STATE_SESSION_KEY] = state
    query = urlencode(
        {
            "client_id": app_config.github.stats_oauth.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "allow_signup": "false",
        }
    )
    return f"{GITHUB_AUTHORIZE_URL}?{query}"


def take_state_matches(received: str | None, cache: MutableMapping) -> bool:
    """Whether received is the state saved for this session. The saved state is removed
    whatever the answer, so each one can only be used once."""
    expected = cache.pop(STATE_SESSION_KEY, None)
    if not isinstance(expected, str) or not expected or not received:
        return False
    return hmac.compare_digest(expected.encode(), received.encode())


def safe_next_path(path: str | None) -> str | None:
    """path if it's a relative Repository Stats path, otherwise None."""
    if not isinstance(path, str):
        return None
    path = path.removesuffix("?")
    if (
        not path.startswith(STATS_PATH_PREFIX)
        or "\\" in path
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
    ):
        return None
    parts = urlsplit(path)
    if parts.scheme or parts.netloc or ".." in parts.path.split("/"):
        return None
    return path


def fetch_github_login(code: str, redirect_uri: str) -> str:
    """Swap the OAuth code for a token, then read the user's login with it."""
    oauth = app_config.github.stats_oauth
    try:
        token_response = requests.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": oauth.client_id,
                "client_secret": oauth.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise GitHubUnavailableError(
            f"GitHub token exchange failed: {type(error).__name__}"
        ) from None
    if token_response.status_code >= 500:
        raise GitHubUnavailableError(
            f"GitHub token exchange failed with status {token_response.status_code}"
        )
    body = _json(token_response)
    access_token = body.get("access_token") if token_response.ok else None
    if not isinstance(access_token, str) or not access_token:
        # GitHub's error codes (e.g. "bad_verification_code") are safe to log.
        error_code = body.get("error")
        error_code = (
            error_code
            if isinstance(error_code, str) and re.fullmatch(r"[a-z_]{1,64}", error_code)
            else "none"
        )
        raise GitHubSignInError(
            f"GitHub token exchange failed with status {token_response.status_code}"
            f" (error: {error_code})"
        )

    try:
        user_response = requests.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise GitHubUnavailableError(
            f"GitHub user lookup failed: {type(error).__name__}"
        ) from None
    if user_response.status_code >= 500:
        raise GitHubUnavailableError(
            f"GitHub user lookup failed with status {user_response.status_code}"
        )
    if user_response.status_code != 200:
        raise GitHubSignInError(
            f"GitHub user lookup failed with status {user_response.status_code}"
        )
    login = _json(user_response).get("login")
    if not isinstance(login, str) or not GITHUB_LOGIN_PATTERN.match(login):
        raise GitHubSignInError("GitHub user lookup returned no valid login")
    return login


def _json(response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
