"""Installation-scoped GitHub transport; collection policy belongs to callers."""

import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from threading import Lock
from time import monotonic, perf_counter, sleep, time
from typing import Any
from urllib.parse import urlsplit

import jwt
import requests
from github import GithubException, GithubRetry
from requests.adapters import HTTPAdapter
from urllib3.exceptions import MaxRetryError
from urllib3.response import HTTPResponse


logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = (10, 60)


class GitHubApiError(ValueError):
    def __init__(
        self, status_code: int, message: str, *,
        request_id: str | None = None, accepted_permissions: str | None = None,
    ):
        self.status_code = status_code
        self.message = message
        self.request_id = request_id
        self.accepted_permissions = accepted_permissions
        super().__init__(f"GitHub API returned HTTP {status_code}: {message}")


class GitHubRequestCoordinator:
    """Share a cooldown between workers using the same installation quota."""

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


class _RawResponseGithubRetry(CoordinatedGithubRetry):
    """Let the adapter classify 403s once Requests has cached their body."""

    def __init__(self, coordinator: GitHubRequestCoordinator, **kwargs):
        kwargs["raise_on_status"] = False
        super().__init__(coordinator, **kwargs)
        self.status_forcelist = [code for code in self.status_forcelist if code != 403]


class CoordinatedGitHubAdapter(HTTPAdapter):
    def __init__(self, coordinator: GitHubRequestCoordinator):
        self.coordinator = coordinator
        super().__init__(
            max_retries=_RawResponseGithubRetry(coordinator, total=3, backoff_factor=1)
        )

    def send(self, request, **kwargs):
        self.coordinator.wait()
        kwargs["timeout"] = kwargs.get("timeout") or REQUEST_TIMEOUT
        started = perf_counter()
        try:
            response = super().send(request, **kwargs)
            retry = self.max_retries
            while (
                response.status_code == 403 and request.method in retry.allowed_methods
            ):
                try:
                    retry = retry.increment(
                        request.method,
                        request.url,
                        HTTPResponse(
                            status=403,
                            headers=response.headers,
                            body=BytesIO(response.content),
                            preload_content=False,
                        ),
                    )
                except (GithubException, MaxRetryError):
                    break
                response.close()
                self.coordinator.wait()
                response = super().send(request, **kwargs)
            logger.debug(
                "GitHub REST %s %s status=%s duration=%.2fs remaining=%s reset=%s",
                request.method,
                request.path_url.split("?")[0],
                response.status_code,
                perf_counter() - started,
                response.headers.get("X-RateLimit-Remaining"),
                response.headers.get("X-RateLimit-Reset"),
            )
            return response
        finally:
            self.coordinator.record_request(perf_counter() - started)


def create_installation_token(
    app_id: str, private_key: str, installation_id: int
) -> dict:
    now_ts = int(time())
    encoded_jwt = jwt.encode(
        {"iat": now_ts, "exp": now_ts + 600, "iss": app_id},
        private_key,
        algorithm="RS256",
    )
    response = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {encoded_jwt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "token": data["token"],
        "expires_at": datetime.strptime(
            data["expires_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc),
    }


class GitHubAppClient:
    """Use one client/session per worker and one coordinator per installation."""

    def __init__(
        self,
        app_client_id: str,
        app_private_key: str,
        app_installation_id: int,
        base_url: str = "https://api.github.com",
        request_coordinator: GitHubRequestCoordinator | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.app_client_id = app_client_id
        self.app_private_key = app_private_key
        self.app_installation_id = app_installation_id
        self.__token = None
        self.__token_expires_at = datetime.fromtimestamp(0, tz=timezone.utc)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json"})
        if request_coordinator is not None:
            self.session.mount(
                "https://", CoordinatedGitHubAdapter(request_coordinator)
            )

    def get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if not self.__token or now >= self.__token_expires_at:
            token_data = create_installation_token(
                self.app_client_id, self.app_private_key, self.app_installation_id
            )
            self.__token = token_data["token"]
            self.__token_expires_at = min(
                token_data["expires_at"], now + timedelta(minutes=55)
            )
        return self.__token

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Return the raw response, including error statuses, for caller policy."""
        target = urlsplit(path)
        if target.scheme or target.netloc:
            base = urlsplit(self.base_url)
            if (target.scheme, target.netloc) != (base.scheme, base.netloc):
                raise ValueError(
                    "Refusing to send the GitHub token to a non-GitHub URL"
                )
            url = path
        else:
            url = f"{self.base_url}/{path.lstrip('/')}"
        self.session.headers.update({"Authorization": f"Bearer {self.get_token()}"})
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        return self.session.request(method, url, **kwargs)

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def request_json(self, method: str, path: str, **kwargs) -> Any:
        response = self.request(method, path, **kwargs)
        if not response.ok:
            try:
                error_message = response.json().get("message", response.text)
            except ValueError:
                error_message = response.text
            raise GitHubApiError(
                response.status_code, str(error_message),
                request_id=response.headers.get("X-GitHub-Request-Id"),
                accepted_permissions=response.headers.get("X-Accepted-GitHub-Permissions"),
            )
        return response.json()

    def close(self):
        self.session.close()
