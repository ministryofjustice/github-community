import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from app.projects.repository_standards.services.github_service import GithubService


class TestGithubService(unittest.TestCase):
    def test_caches_maintainer_count_and_passes_it_to_factory(self):
        service = GithubService.__new__(GithubService)
        service.organisation_name = "ministryofjustice"
        service.github_client_core_api = Mock()
        service.github_client = Mock()
        service.github_client.get_team_maintainer_count.return_value = 2

        repositories = [
            SimpleNamespace(name="repo-one", archived=False, fork=False),
            SimpleNamespace(name="repo-two", archived=False, fork=False),
        ]
        organization = service.github_client_core_api.get_organization.return_value
        organization.get_repos.return_value = repositories

        with (
            patch.object(
                service,
                "_GithubService__get_teams_with_access",
                return_value=(["team-alpha"], [], ["team-alpha"], []),
            ),
            patch(
                "app.projects.repository_standards.services.github_service.RepositoryInfoFactory.from_github_repo",
                side_effect=lambda repo, *args: repo.name,
            ) as factory,
        ):
            result = service.get_repositories()

        self.assertEqual(result, ["repo-one", "repo-two"])
        service.github_client.get_team_maintainer_count.assert_called_once_with(
            "team-alpha"
        )
        self.assertEqual(
            [factory_call.args[-1] for factory_call in factory.call_args_list],
            [{"team-alpha": 2}, {"team-alpha": 2}],
        )