from calendar import timegm
from time import gmtime, sleep
from typing import Callable, List

from github import Github, RateLimitExceededException, Auth
from github.Repository import Repository
from github.Team import Team
import logging

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
    ) -> list[dict]:
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
            if not (repository.archived or repository.fork)
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
            try:
                default_branch_protection = repo.get_branch(
                    repo.default_branch
                ).get_protection()
            except Exception:
                default_branch_protection = None
            pr = (
                default_branch_protection.required_pull_request_reviews
                if default_branch_protection
                else None
            )

            response.append(
                {
                    "name": repo.name,
                    "github_teams_with_admin_access": teams_with_admin_access,
                    "github_teams_with_admin_access_parents": teams_with_admin_access_parents,
                    "github_teams_with_any_access": teams_with_any_access,
                    "github_teams_with_any_access_parents": teams_with_any_access_parents,
                    "visibility": repo.visibility,
                    "description": repo.description,
                    "license": repo.license.key if repo.license else None,
                    "delete_branch_on_merge": repo.delete_branch_on_merge,
                    "security_and_analysis_secret_scanning_status": repo.security_and_analysis.secret_scanning.status
                    if repo.security_and_analysis.secret_scanning
                    else None,
                    "security_and_analysis_secret_scanning_validity_checks": repo.security_and_analysis.secret_scanning_validity_checks.status
                    if repo.security_and_analysis.secret_scanning_validity_checks
                    else None,
                    "security_and_analysis_push_protection_status": repo.security_and_analysis.secret_scanning_push_protection.status
                    if repo.security_and_analysis.secret_scanning_push_protection
                    else None,
                    "security_and_analysis_advanced_security": repo.security_and_analysis.advanced_security.status
                    if repo.security_and_analysis.advanced_security
                    else None,
                    "secret_scanning_non_provider_patterns": repo.security_and_analysis.secret_scanning_non_provider_patterns.status
                    if repo.security_and_analysis.secret_scanning_non_provider_patterns
                    else None,
                    "default_branch_name": repo.default_branch,
                    "default_branch_protection_enabled": default_branch_protection.enabled
                    if default_branch_protection
                    else None,
                    "default_branch_protection_allow_force_pushes": default_branch_protection.allow_force_pushes
                    if default_branch_protection
                    else None,
                    "default_branch_protection_enforce_admins": default_branch_protection.enforce_admins
                    if default_branch_protection
                    else None,
                    "default_branch_protection_required_signatures": default_branch_protection.required_signatures
                    if default_branch_protection
                    else None,
                    "default_branch_protection_pr_dismiss_stale_reviews": pr.dismiss_stale_reviews
                    if pr
                    else None,
                    "default_branch_protection_pr_require_code_owner_reviews": pr.require_code_owner_reviews
                    if pr
                    else None,
                    "default_branch_protection_pr_require_last_push_approval": pr.require_last_push_approval
                    if pr
                    else None,
                    "default_branch_protection_pr_required_approving_review_count": pr.required_approving_review_count
                    if pr
                    else None,
                },
            )
            counter += 1
        return response
