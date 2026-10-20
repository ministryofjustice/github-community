"""Minimal GitHub App REST client for Repository Stats.

A small local copy of the installation-token pattern in Repository Standards'
github_client.py, so this project doesn't import Repository Standards code.
"""

from datetime import UTC, datetime, timedelta
from time import time

import jwt
import requests

GITHUB_API_URL = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS = 10


def create_installation_token(
    app_id: str, private_key: str, installation_id: int
) -> str:
    now_ts = int(time())
    encoded_jwt = jwt.encode(
        {"iat": now_ts, "exp": now_ts + 600, "iss": app_id},
        private_key,
        algorithm="RS256",
    )
    response = requests.post(
        f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {encoded_jwt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["token"]


class GitHubAppClient:
    def __init__(
        self, app_client_id: str, app_private_key: str, app_installation_id: int
    ):
        self.app_client_id = app_client_id
        self.app_private_key = app_private_key
        self.app_installation_id = app_installation_id
        self.__token: str | None = None
        self.__token_expires_at = datetime.fromtimestamp(0, tz=UTC)

    def __get_token(self) -> str:
        now = datetime.now(UTC)
        if not self.__token or now >= self.__token_expires_at:
            self.__token = create_installation_token(
                self.app_client_id, self.app_private_key, self.app_installation_id
            )
            self.__token_expires_at = now + timedelta(minutes=55)
        return self.__token

    def get(self, path: str) -> requests.Response:
        """GET a REST API path, or a full api.github.com URL such as a pagination "next" link.

        Returns the response whatever its status.
        """
        if path.startswith(("http://", "https://")):
            if not path.startswith(f"{GITHUB_API_URL}/"):
                raise ValueError(
                    "Refusing to send the GitHub token to a non-GitHub URL"
                )
            url = path
        else:
            url = f"{GITHUB_API_URL}{path}"
        return requests.get(
            url,
            headers={
                "Authorization": f"Bearer {self.__get_token()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
