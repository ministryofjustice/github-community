import logging
from calendar import timegm
from time import gmtime, sleep, time
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List

import jwt
import requests
from github import RateLimitExceededException

logger = logging.getLogger(__name__)


def retries_github_rate_limit_exception_at_next_reset_once(func: Callable) -> Callable:
    def decorator(*args, **kwargs):
        """
        A decorator to retry the method when rate limiting for GitHub resets if the method fails due to Rate Limit related exception.

        WARNING: Since this decorator retries methods, ensure that the method being decorated is idempotent
         or contains only one non-idempotent method at the end of a call chain to GitHub.

         Example of idempotent methods are:
            - Retrieving data
         Example of (potentially) non-idempotent methods are:
            - Deleting data
            - Updating data
        """
        try:
            return func(*args, **kwargs)
        except RateLimitExceededException as exception:
            logger.warning(
                f"Caught {type(exception).__name__}, retrying calls when rate limit resets."
            )
            rate_limits = args[0].github_client_core_api.get_rate_limit()
            rate_limit_to_use = (
                rate_limits.core
                if isinstance(exception, RateLimitExceededException)
                else rate_limits.graphql
            )

            reset_timestamp = timegm(rate_limit_to_use.reset.timetuple())
            now_timestamp = timegm(gmtime())
            time_until_core_api_rate_limit_resets = (
                (reset_timestamp - now_timestamp)
                if reset_timestamp > now_timestamp
                else 0
            )

            wait_time_buffer = 5
            sleep(
                time_until_core_api_rate_limit_resets + wait_time_buffer
                if time_until_core_api_rate_limit_resets
                else 0
            )
            return func(*args, **kwargs)

    return decorator


def create_installation_token(
    app_id: str, private_key: str, installation_id: int
) -> dict:
    """
    Create a GitHub App installation token.

    Returns:
        dict: { "token": str, "expires_at": datetime }
    """
    now_ts = int(time())
    payload = {
        "iat": now_ts,
        "exp": now_ts + 600,  # max 10 minutes
        "iss": app_id,
    }
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")

    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {encoded_jwt}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    return {
        "token": data["token"],
        "expires_at": datetime.strptime(
            data["expires_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc),
    }


class GitHubClient:
    def __init__(
        self,
        app_client_id: str,
        app_private_key: str,
        app_installation_id: int,
        org: str,
        base_url: str = "https://api.github.com",
    ):
        self.org = org
        self.base_url = base_url.rstrip("/")
        self.app_client_id = app_client_id
        self.app_private_key = app_private_key
        self.app_installation_id = app_installation_id

        self.__token = None
        self.__token_expires_at = datetime.fromtimestamp(0, tz=timezone.utc)

        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json"})

    def __get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if not self.__token or now >= self.__token_expires_at:
            token_data = create_installation_token(
                self.app_client_id,
                self.app_private_key,
                self.app_installation_id,
            )
            self.__token = token_data["token"]
            self.__token_expires_at = now + timedelta(minutes=55)
        return self.__token

    def __call(self, method: str, path: str, **kwargs) -> Any:
        """Internal request helper."""
        self.session.headers.update({"Authorization": f"Bearer {self.__get_token()}"})

        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, **kwargs)

        if not response.ok:
            raise ValueError(
                f"Error calling URL: [{url}], Status Code: [{response.status_code}], Response: {response.text}"
            )

        return response.json()

    def get_branch_rulesets(self, repo: str, branch: str) -> List[Dict[str, Any]]:
        """
        List branch rulesets for a given repository.
        Docs: https://docs.github.com/en/rest/repos/rules?apiVersion=2022-11-28#list-repository-rulesets
        """
        return self.__call("GET", f"/repos/{self.org}/{repo}/rules/branches/{branch}")

    def get_repository_ruleset(self, repo: str, ruleset_id: str) -> Dict[str, Any]:
        """
        Get a ruleset for a repository.
        Docs: https://docs.github.com/en/rest/repos/rules?apiVersion=2022-11-28#get-a-repository-ruleset
        """
        return self.__call("GET", f"/repos/{self.org}/{repo}/rulesets/{ruleset_id}")
