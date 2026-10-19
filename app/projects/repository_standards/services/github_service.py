import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local
from time import perf_counter
from typing import List

from github import Auth, Github
from github.Repository import Repository
from github.Team import Team

from app.projects.repository_standards.clients.github_client import (
    retries_github_rate_limit_exception_at_next_reset_once,
    GitHubClient,
    GitHubRequestCoordinator,
    CoordinatedGithubRetry,
)
from app.projects.repository_standards.models.repository_info import (
    RepositoryInfo,
    RepositoryInfoFactory,
)

logger = logging.getLogger(__name__)


class GithubService:
    def __init__(
        self,
        app_client_id: str,
        app_private_key: str,
        app_installation_id: int,
        request_coordinator: GitHubRequestCoordinator | None = None,
    ) -> None:
        self._credentials = (app_client_id, app_private_key, app_installation_id)
        self._request_coordinator = request_coordinator or GitHubRequestCoordinator()
        self.organisation_name: str = "ministryofjustice"
        app_auth = Auth.AppAuth(app_client_id, app_private_key)
        app_installation_auth = app_auth.get_installation_auth(app_installation_id)
        self.github_client_core_api: Github = Github(
            auth=app_installation_auth,
            retry=CoordinatedGithubRetry(
                self._request_coordinator, total=3, backoff_factor=1
            ),
        )
        self.github_client = GitHubClient(
            app_client_id=app_client_id,
            app_private_key=app_private_key,
            app_installation_id=app_installation_id,
            org=self.organisation_name,
            request_coordinator=self._request_coordinator,
        )

    def _new_worker_service(self):
        return GithubService(
            *self._credentials, request_coordinator=self._request_coordinator
        )

    @retries_github_rate_limit_exception_at_next_reset_once
    def __get_all_parents_team_names_of_team(
        self, team: Team, team_parent_cache: dict[str, List[str]]
    ) -> list[str]:
        if team.slug in team_parent_cache:
            logging.debug("Teams parents cache hit!")
            return team_parent_cache[team.slug]

        parents = []
        team_to_check = team

        while team_to_check and team_to_check.parent:
            parent_slug = team_to_check.parent.slug
            parents.append(parent_slug)
            team_to_check = team_to_check.parent

        team_parent_cache[team.slug] = parents
        return parents

    @retries_github_rate_limit_exception_at_next_reset_once
    def __get_teams_with_access(
        self,
        repository: Repository,
        teams_to_ignore: List[str],
        team_parent_cache: dict[str, List[str]],
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        teams_with_admin_access = []
        teams_with_admin_access_parents = []
        teams_with_any_access = []
        teams_with_any_access_parents = []

        for team in list(repository.get_teams()):
            logger.debug(f"Processing Team: [ {team.slug} ]")
            if team.slug in teams_to_ignore:
                logging.debug("Team specified to ignore, skipping...")
                continue
            permissions = team.permissions
            team_parents = self.__get_all_parents_team_names_of_team(
                team, team_parent_cache
            )
            if permissions and permissions.admin:
                teams_with_admin_access.append(team.slug)
                teams_with_admin_access_parents.extend(team_parents)
            if permissions and (
                permissions.admin
                or permissions.maintain
                or permissions.push
                or permissions.pull
                or permissions.triage
            ):
                teams_with_any_access.append(team.slug)
                teams_with_any_access_parents.extend(team_parents)
        return (
            teams_with_admin_access,
            teams_with_admin_access_parents,
            teams_with_any_access,
            teams_with_any_access_parents,
        )

    @retries_github_rate_limit_exception_at_next_reset_once
    def _collect_repository(
        self, repo, teams_to_ignore, team_parent_cache, team_maintainer_count_cache
    ) -> RepositoryInfo:
        started = perf_counter()
        (
            teams_with_admin_access,
            teams_with_admin_access_parents,
            teams_with_any_access,
            teams_with_any_access_parents,
        ) = self.__get_teams_with_access(repo, teams_to_ignore, team_parent_cache)
        admin_team_maintainer_counts = {}
        for team_slug in teams_with_admin_access:
            if team_slug not in team_maintainer_count_cache:
                team_maintainer_count_cache[team_slug] = (
                    self.github_client.get_team_maintainer_count(team_slug)
                )
            admin_team_maintainer_counts[team_slug] = team_maintainer_count_cache[team_slug]

        result = RepositoryInfoFactory.from_github_repo(
            repo,
            teams_with_admin_access,
            teams_with_admin_access_parents,
            teams_with_any_access,
            teams_with_any_access_parents,
            self.github_client,
            admin_team_maintainer_counts,
        )
        logger.info("Collected repository %s in %.2fs", repo.name, perf_counter() - started)
        return result

    def get_repositories(
        self,
        repo_name: str | None = None,
        limit: int = 1500,
        teams_to_ignore: List[str] = [
            "organisation-security-auditor",
            "organisation-security-auditor-external",
            "organisation-security-auditor-architects",
        ],
        workers: int = 1,
    ) -> List[RepositoryInfo]:
        if not 1 <= workers <= 8:
            raise ValueError("GitHub collection workers must be between 1 and 8")
        started = perf_counter()
        response = []
        team_parent_cache = {}
        team_maintainer_count_cache = {}
        repositories: list
        if not repo_name:
            repositories = list(
                self.github_client_core_api.get_organization(
                    self.organisation_name
                ).get_repos(type="public")
            )
        else:
            repositories = [
                self.github_client_core_api.get_organization(
                    self.organisation_name
                ).get_repo(name=repo_name)
            ]
        repositories_to_check = [
            repository
            for repository in repositories
            if not (repository.archived or repository.fork)
        ]
        logger.info(f"Total Repositories: [ {len(repositories_to_check)} ]")
        if len(repositories_to_check) > limit:
            logger.info("Limit reached: collecting only %s repositories", limit)
            repositories_to_check = repositories_to_check[:limit]
        logger.info(
            "GitHub collection: workers=%s repositories=%s discovery=%.2fs",
            workers, len(repositories_to_check), perf_counter() - started,
        )
        if workers > 1:
            response = self._collect_concurrently(
                repositories_to_check, teams_to_ignore, workers
            )
            self._log_collection_summary(started, workers, len(response))
            return response
        counter = 1
        for repo in repositories_to_check:
            if counter > limit:
                logger.info("Limit Reached, exiting early")
                break
            logger.info(
                f"Processing Repository: [ {repo.name} ] {counter}/{len(repositories_to_check)}"
            )
            response.append(
                self._collect_repository(
                    repo, teams_to_ignore, team_parent_cache, team_maintainer_count_cache
                )
            )
            counter += 1
        self._log_collection_summary(started, workers, len(response))
        return response

    def _log_collection_summary(self, started, workers, count):
        coordinator = getattr(self, "_request_coordinator", None)
        logger.info(
            "GitHub collection complete: repositories=%s workers=%s elapsed=%.2fs "
            "custom_rest_requests=%s custom_rest_request_seconds=%.2f",
            count, workers, perf_counter() - started,
            coordinator.request_count if coordinator else 0,
            coordinator.request_seconds if coordinator else 0,
        )

    def _collect_concurrently(self, repositories, teams_to_ignore, workers):
        worker_state = local()
        worker_services = []
        registry_lock = Lock()

        def collect(item):
            index, repository_name = item
            if not hasattr(worker_state, "service"):
                worker_state.service = self._new_worker_service()
                worker_state.parents = {}
                worker_state.maintainers = {}
                with registry_lock:
                    worker_services.append(worker_state.service)
            worker = worker_state.service
            self._request_coordinator.wait()
            repo = worker.github_client_core_api.get_repo(
                f"{self.organisation_name}/{repository_name}", lazy=True
            )
            logger.info(
                "Processing Repository: [ %s ] %s/%s",
                repository_name, index, len(repositories),
            )
            return worker._collect_repository(
                repo, teams_to_ignore, worker_state.parents, worker_state.maintainers
            )

        try:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="github-collector") as executor:
                futures = {
                    executor.submit(collect, (index + 1, repo.name)): index
                    for index, repo in enumerate(repositories)
                }
                results = {}
                try:
                    for future in as_completed(futures):
                        results[futures[future]] = future.result()
                        logger.info("Repository collection progress: %s/%s complete", len(results), len(repositories))
                except Exception:
                    for future in futures:
                        future.cancel()
                    raise
                return [results[index] for index in range(len(repositories))]
        finally:
            for worker in worker_services:
                worker.github_client_core_api.close()
                worker.github_client.session.close()
