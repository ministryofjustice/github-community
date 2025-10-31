import logging
from typing import List

from github import Auth, Github
from github.Repository import Repository
from github.Team import Team

from app.projects.repository_standards.clients.github_client import (
    retries_github_rate_limit_exception_at_next_reset_once,
    GitHubClient,
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
    ) -> None:
        self.organisation_name: str = "ministryofjustice"
        app_auth = Auth.AppAuth(app_client_id, app_private_key)
        app_installation_auth = app_auth.get_installation_auth(app_installation_id)
        self.github_client_core_api: Github = Github(auth=app_installation_auth)
        self.github_client = GitHubClient(
            app_client_id=app_client_id,
            app_private_key=app_private_key,
            app_installation_id=app_installation_id,
            org=self.organisation_name,
        )

    @retries_github_rate_limit_exception_at_next_reset_once
    def __get_all_parents_team_names_of_team(
        self, team: Team, team_parent_cache: dict[str, List[str]] = {}
    ) -> list[str]:
        if team.name in team_parent_cache:
            logging.info("Teams parents cache hit!")
            return team_parent_cache[team.name]

        parents = []
        team_to_check = team

        while team_to_check and team_to_check.parent:
            parent_name = team_to_check.parent.name
            parents.append(parent_name)
            team_to_check = team_to_check.parent

        team_parent_cache[team.name] = parents
        return parents

    @retries_github_rate_limit_exception_at_next_reset_once
    def __get_teams_with_access(
        self,
        repository: Repository,
        teams_to_ignore: List[str],
        team: Team,
        team_parent_cache: dict[str, List[str]] = {},
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        teams_with_admin_access = []
        teams_with_admin_access_parents = []
        teams_with_any_access = []
        teams_with_any_access_parents = []

        for team in list(repository.get_teams()):
            logger.info(f"Processing Team: [ {team.name} ]")
            if team.name in teams_to_ignore:
                logging.info("Team specified to ignore, skipping...")
                continue
            permissions = team.get_repo_permission(repository)
            team_parents = self.__get_all_parents_team_names_of_team(
                team, team_parent_cache
            )
            if permissions and permissions.admin:
                teams_with_admin_access.append(team.name)
                teams_with_admin_access_parents.extend(team_parents)
            if permissions and (
                permissions.admin
                or permissions.maintain
                or permissions.push
                or permissions.pull
                or permissions.triage
            ):
                teams_with_any_access.append(team.name)
                teams_with_any_access_parents.extend(team_parents)
        return (
            teams_with_admin_access,
            teams_with_admin_access_parents,
            teams_with_any_access,
            teams_with_any_access_parents,
        )

    @retries_github_rate_limit_exception_at_next_reset_once
    def get_all_repositories(
        self,
        limit: int = 1000,
        teams_to_ignore: List[str] = ["organisation-security-auditor"],
    ) -> List[RepositoryInfo]:
        response = []
        team_parent_cache = {}
        repositories = list(
            self.github_client_core_api.get_organization(
                self.organisation_name
            ).get_repos(type="public")
        )
        repositories_to_check = [
            repository
            for repository in repositories
            # if not (repository.archived or repository.fork)
            if repository.name == "github-community"
        ]
        logger.info(f"Total Repositories: [ {len(repositories_to_check)} ]")
        counter = 1
        for repo in repositories_to_check:
            if counter > limit:
                logger.info("Limit Reached, exiting early")
                break
            logger.info(
                f"Processing Repository: [ {repo.name} ] {counter}/{len(repositories_to_check)}"
            )
            (
                teams_with_admin_access,
                teams_with_admin_access_parents,
                teams_with_any_access,
                teams_with_any_access_parents,
            ) = self.__get_teams_with_access(repo, teams_to_ignore, team_parent_cache)

            response.append(
                RepositoryInfoFactory.from_github_repo(
                    repo,
                    teams_with_admin_access,
                    teams_with_admin_access_parents,
                    teams_with_any_access,
                    teams_with_any_access_parents,
                    self.github_client,
                )
            )
            counter += 1
        return response
