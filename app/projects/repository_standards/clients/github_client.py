import logging
from calendar import timegm
from time import gmtime, sleep
from typing import Any, Callable, Dict, List

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


class GitHubClient:
    """
    High-level GitHub API client — wraps GitHub's REST API.
    Used to make calls to GitHub using their API, typically ones that are not supported yet by PyGithub.
    """

    def __init__(self, token: str, org: str, base_url: str = "https://api.github.com"):
        self.org = org
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "MoJ-GitHubClient",
            }
        )

    def __call(self, method: str, path: str, **kwargs) -> Any:
        """Internal request helper."""
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, **kwargs)

        if not response.ok:
            raise ValueError(
                f"Error calling URL: [{url}], Status Code: [{response.status_code}], Response: {response.text} "
            )

        return response.json()

    def get_branch_rulesets(self, repo: str, branch: str) -> List[Dict[str, Any]]:
        """
        List branch rulesets for a given repository.
        Docs: https://docs.github.com/en/rest/repos/rules?apiVersion=2022-11-28#list-repository-rulesets
        """
        return self.__call("GET", f"/repos/{self.org}/{repo}/rules/branches/{branch}")
