"""GitHub App REST client for Repository Stats.

Token creation, caching and the GitHub-only URL check come from the shared client
used by Repository Standards. Each installation gets its own client, token and session.
Stats keeps its 10-second timeout for token creation and API requests.
"""

from app.shared.services.github_app_client import (
    GitHubAppClient as SharedGitHubAppClient,
)
from app.shared.services.github_app_client import (
    GitHubRequestCoordinator,
)

GITHUB_API_VERSION = "2022-11-28"


class GitHubAppClient(SharedGitHubAppClient):
    def __init__(
        self,
        app_client_id: str,
        app_private_key: str,
        app_installation_id: int,
        request_coordinator: GitHubRequestCoordinator | None = None,
    ):
        super().__init__(
            app_client_id,
            app_private_key,
            app_installation_id,
            request_coordinator=request_coordinator,
            timeout=10,
        )
        # Read by the Repository Stats getters to avoid retrying what the coordinated
        # transport already retried.
        self.request_coordinator = request_coordinator
        self.session.headers["X-GitHub-Api-Version"] = GITHUB_API_VERSION
