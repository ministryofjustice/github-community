import logging
from calendar import timegm
from time import gmtime, sleep, time
from time import monotonic, perf_counter
from threading import Lock
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List

import jwt
import requests
from github import GithubRetry, RateLimitExceededException
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)


class GitHubRequestCoordinator:
    def __init__(self):
        self._lock = Lock()
        self._resume_at = 0.0
        self.request_count = 0
        self.request_seconds = 0.0

    def defer(self, seconds: float):
        with self._lock:
            self._resume_at = max(self._resume_at, monotonic() + max(seconds, 0))
        logger.warning("GitHub shared rate-limit cooldown: %.1fs", seconds)

    def wait(self):
        while True:
            with self._lock:
                remaining = self._resume_at - monotonic()
            if remaining <= 0:
                return
            sleep(remaining)

    def record_request(self, seconds: float):
        with self._lock:
            self.request_count += 1
            self.request_seconds += seconds


class CoordinatedGithubRetry(GithubRetry):
    def __init__(self, coordinator: GitHubRequestCoordinator, **kwargs):
        self.coordinator = coordinator
        kwargs.setdefault("status_forcelist", [429, *range(500, 600)])
        kwargs.setdefault("allowed_methods", frozenset({"GET", "HEAD"}))
        super().__init__(**kwargs)

    def new(self, **kwargs):
        kwargs["coordinator"] = self.coordinator
        return super().new(**kwargs)

    def increment(self, method=None, url=None, response=None, **kwargs):
        retry = super().increment(method, url, response, **kwargs)
        if response is not None and response.status in (403, 429):
            delay = retry.get_retry_after(response)
            self.coordinator.defer(
                delay if delay is not None else max(retry.get_backoff_time(), 60)
            )
        return retry

    def sleep(self, response=None):
        if response is not None and response.status in (403, 429):
            self.coordinator.wait()
        else:
            super().sleep(response)


class CoordinatedGitHubAdapter(HTTPAdapter):
    def __init__(self, coordinator: GitHubRequestCoordinator):
        self.coordinator = coordinator
        super().__init__(max_retries=CoordinatedGithubRetry(
            coordinator, total=3, backoff_factor=1
        ))

    def send(self, request, **kwargs):
        self.coordinator.wait()
        kwargs["timeout"] = kwargs.get("timeout") or (10, 60)
        started = perf_counter()
        try:
            response = super().send(request, **kwargs)
            logger.debug(
                "GitHub REST %s %s status=%s duration=%.2fs remaining=%s reset=%s",
                request.method, request.path_url.split("?")[0], response.status_code,
                perf_counter() - started, response.headers.get("X-RateLimit-Remaining"),
                response.headers.get("X-RateLimit-Reset"),
            )
            return response
        finally:
            self.coordinator.record_request(perf_counter() - started)


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
        request_coordinator: GitHubRequestCoordinator | None = None,
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
        if request_coordinator is not None:
            self.session.mount("https://", CoordinatedGitHubAdapter(request_coordinator))

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

    def __get_paginated_repository_alerts(self, path: str) -> List[Dict[str, Any]]:
        alerts = []
        page = 1
        while True:
            page_alerts = self.__call(
                "GET",
                path,
                params={"state": "open", "per_page": 100, "page": page},
            )
            alerts.extend(page_alerts)
            if len(page_alerts) < 100:
                return alerts
            page += 1

    def get_open_code_scanning_alerts(self, repo: str) -> List[Dict[str, Any]]:
        return self.__get_paginated_repository_alerts(
            f"/repos/{self.org}/{repo}/code-scanning/alerts"
        )

    def get_open_dependabot_alerts(self, repo: str) -> List[Dict[str, Any]]:
        alerts = []
        url = f"{self.base_url}/repos/{self.org}/{repo}/dependabot/alerts"
        params = {"state": "open", "per_page": 100}
        self.session.headers.update({"Authorization": f"Bearer {self.__get_token()}"})

        while url:
            response = self.session.get(url, params=params)
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