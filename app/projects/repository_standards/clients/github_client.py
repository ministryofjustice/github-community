import logging
from calendar import timegm
from time import gmtime, sleep
from typing import Any, Callable, Dict, List

from github import RateLimitExceededException

from app.shared.services.github_app_client import (
    CoordinatedGithubRetry as CoordinatedGithubRetry,
    CoordinatedGitHubAdapter as CoordinatedGitHubAdapter,
    GitHubApiError as GitHubApiError,
    GitHubAppClient,
    GitHubRequestCoordinator as GitHubRequestCoordinator,
    create_installation_token as create_installation_token,
)

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
            wait_seconds = (
                time_until_core_api_rate_limit_resets + wait_time_buffer
                if time_until_core_api_rate_limit_resets
                else 0
            )
            coordinator = getattr(args[0], "_request_coordinator", None)
            if coordinator is not None:
                coordinator.defer(wait_seconds)
                coordinator.wait()
            else:
                sleep(wait_seconds)
            return func(*args, **kwargs)

    return decorator


class GitHubClient(GitHubAppClient):
    def __init__(
        self,
        app_client_id: str,
        app_private_key: str,
        app_installation_id: int,
        org: str,
        base_url: str = "https://api.github.com",
        request_coordinator: GitHubRequestCoordinator | None = None,
    ):
        self.org = org
        super().__init__(
            app_client_id, app_private_key, app_installation_id,
            base_url=base_url, request_coordinator=request_coordinator,
        )

    def __call(self, method: str, path: str, **kwargs) -> Any:
        return self.request_json(method, path, **kwargs)

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

    def get_repository_custom_properties(self, repo: str) -> Dict[str, Any]:
        values = self.__call(
            "GET",
            f"/repos/{self.org}/{repo}/properties/values",
        )
        return {
            item["property_name"]: item.get("value")
            for item in values
            if "property_name" in item
        }

    def get_codeowners_errors(self, repo: str) -> Dict[str, Any]:
        return self.__call(
            "GET",
            f"/repos/{self.org}/{repo}/codeowners/errors",
        )

    def __get_paginated_repository_alerts(self, path: str, extra_params=None) -> List[Dict[str, Any]]:
        alerts = []
        page = 1
        while True:
            page_alerts = self.__call(
                "GET",
                path,
                params={"state": "open", "per_page": 100, "page": page, **(extra_params or {})},
            )
            alerts.extend(page_alerts)
            if len(page_alerts) < 100:
                return alerts
            page += 1

    def get_open_code_scanning_alerts(self, repo: str) -> List[Dict[str, Any]]:
        return self.__get_paginated_repository_alerts(
            f"/repos/{self.org}/{repo}/code-scanning/alerts"
        )

    def get_code_scanning_default_setup(self, repo: str) -> Dict[str, Any]:
        return self.__call(
            "GET", f"/repos/{self.org}/{repo}/code-scanning/default-setup"
        )

    def get_repository_languages(self, repo: str) -> Dict[str, int]:
        return self.__call("GET", f"/repos/{self.org}/{repo}/languages")

    def get_open_secret_scanning_alerts(self, repo: str) -> List[Dict[str, Any]]:
        try:
            alerts = self.__get_paginated_repository_alerts(
                f"/repos/{self.org}/{repo}/secret-scanning/alerts",
                extra_params={"hide_secret": "true"},
            )
            if any(alert.get("state") not in {"open", "resolved"} for alert in alerts):
                raise ValueError("Invalid secret alert state")
            return [{"state": alert["state"]} for alert in alerts]
        except Exception:
            raise ValueError("Secret Scanning alert data could not be retrieved") from None

    def get_open_dependabot_alerts(self, repo: str) -> List[Dict[str, Any]]:
        alerts = []
        url = f"{self.base_url}/repos/{self.org}/{repo}/dependabot/alerts"
        params = {"state": "open", "per_page": 100}
        while url:
            response = self.get(url, params=params)
            if not response.ok:
                raise ValueError(
                    f"Error calling URL: [{url}], Status Code: "
                    f"[{response.status_code}], Response: {response.text}"
                )

            alerts.extend(response.json())
            url = response.links.get("next", {}).get("url")
            params = None

        return alerts

    def get_team_maintainer_count(self, team_slug: str) -> int:
        members = self.__call(
            "GET",
            f"/orgs/{self.org}/teams/{team_slug}/members",
            params={"role": "maintainer", "per_page": 2},
        )
        return min(len(members), 2)