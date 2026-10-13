import unittest
from unittest.mock import patch

from app.projects.repository_standards.clients.github_client import GitHubClient


class TestRepositoryCustomProperties(unittest.TestCase):
    def test_returns_custom_properties_by_name(self):
        client = GitHubClient(
            app_client_id="client",
            app_private_key="key",
            app_installation_id=123,
            org="ministryofjustice",
        )
        with patch.object(
            client,
            "_GitHubClient__call",
            return_value=[
                {"property_name": "business-unit", "value": "Example Business Unit"},
                {"property_name": "other-property", "value": "some value"},
            ],
        ) as github_call:
            result = client.get_repository_custom_properties("example-repo")

        self.assertEqual(
            result,
            {
                "business-unit": "Example Business Unit",
                "other-property": "some value",
            },
        )
        github_call.assert_called_once_with(
            "GET",
            "/repos/ministryofjustice/example-repo/properties/values",
        )
        
class TestTeamMaintainerCount(unittest.TestCase):
    def test_counts_team_maintainers_up_to_two(self):
        client = GitHubClient(
            app_client_id="client",
            app_private_key="key",
            app_installation_id=123,
            org="ministryofjustice",
        )
        with patch.object(
            client,
            "_GitHubClient__call",
            return_value=[{"login": "maintainer-one"}, {"login": "maintainer-two"}],
        ) as github_call:
            count = client.get_team_maintainer_count("team-alpha")

        self.assertEqual(count, 2)
        github_call.assert_called_once_with(
            "GET",
            "/orgs/ministryofjustice/teams/team-alpha/members",
            params={"role": "maintainer", "per_page": 2},
        )

    def test_returns_count_below_two(self):
        client = GitHubClient(
            app_client_id="client",
            app_private_key="key",
            app_installation_id=123,
            org="ministryofjustice",
        )
        with patch.object(
            client,
            "_GitHubClient__call",
            return_value=[{"login": "maintainer-one"}],
        ):
            self.assertEqual(client.get_team_maintainer_count("team-alpha"), 1)


class TestRepositorySecurityAlerts(unittest.TestCase):
    def setUp(self):
        self.client = GitHubClient(
            app_client_id="client",
            app_private_key="key",
            app_installation_id=123,
            org="ministryofjustice",
        )

    def test_gets_open_code_scanning_alerts_across_pages(self):
        with patch.object(
            self.client,
            "_GitHubClient__call",
            side_effect=[[{}] * 100, [{"state": "open"}]],
        ) as github_call:
            alerts = self.client.get_open_code_scanning_alerts("example-repo")

        self.assertEqual(len(alerts), 101)
        self.assertEqual(github_call.call_count, 2)
        github_call.assert_any_call(
            "GET",
            "/repos/ministryofjustice/example-repo/code-scanning/alerts",
            params={"state": "open", "per_page": 100, "page": 1},
        )
        github_call.assert_any_call(
            "GET",
            "/repos/ministryofjustice/example-repo/code-scanning/alerts",
            params={"state": "open", "per_page": 100, "page": 2},
        )

    def test_gets_open_dependabot_alerts(self):
        with patch.object(
            self.client,
            "_GitHubClient__call",
            return_value=[{"state": "open"}],
        ) as github_call:
            alerts = self.client.get_open_dependabot_alerts("example-repo")

        self.assertEqual(alerts, [{"state": "open"}])
        github_call.assert_called_once_with(
            "GET",
            "/repos/ministryofjustice/example-repo/dependabot/alerts",
            params={"state": "open", "per_page": 100, "page": 1},
        )


class TestCodeownersErrors(unittest.TestCase):
    def test_gets_codeowners_validation_errors(self):
        client = GitHubClient(
            app_client_id="client",
            app_private_key="key",
            app_installation_id=123,
            org="ministryofjustice",
        )
        with patch.object(
            client,
            "_GitHubClient__call",
            return_value={"errors": []},
        ) as github_call:
            result = client.get_codeowners_errors("example-repo")

        self.assertEqual(result, {"errors": []})
        github_call.assert_called_once_with(
            "GET",
            "/repos/ministryofjustice/example-repo/codeowners/errors",
        )