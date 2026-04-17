import unittest
from unittest.mock import MagicMock, patch

from app.projects.repository_standards.clients.github_client import GitHubClient
from app.projects.repository_standards.services.github_service import GithubService


class TestGitHubClientCustomProperties(unittest.TestCase):
    def test_update_repository_custom_properties_calls_expected_endpoint(self):
        client = GitHubClient(
            app_client_id="client-id",
            app_private_key="private-key",
            app_installation_id=123,
            org="ministryofjustice",
        )

        properties = [{"property_name": "repository-standard", "value": "baseline"}]

        with patch.object(client, "_GitHubClient__call", return_value={}) as mock_call:
            client.update_repository_custom_properties("test-repo", properties)

        mock_call.assert_called_once_with(
            "PATCH",
            "/repos/ministryofjustice/test-repo/properties/values",
            json={"properties": properties},
        )

    def test_update_repository_custom_properties_propagates_errors(self):
        client = GitHubClient(
            app_client_id="client-id",
            app_private_key="private-key",
            app_installation_id=123,
            org="ministryofjustice",
        )

        with patch.object(
            client,
            "_GitHubClient__call",
            side_effect=ValueError("github api failure"),
        ):
            with self.assertRaises(ValueError):
                client.update_repository_custom_properties(
                    "test-repo",
                    [{"property_name": "repository-standard", "value": "baseline"}],
                )


class TestGithubServiceCustomProperties(unittest.TestCase):
    def test_set_repository_standard_custom_property_formats_payload(self):
        service = GithubService.__new__(GithubService)
        service.github_client = MagicMock()

        service.set_repository_standard_custom_property("test-repo", "standard")

        service.github_client.update_repository_custom_properties.assert_called_once_with(
            "test-repo",
            [{"property_name": "repository-standard", "value": "standard"}],
        )

    def test_set_repository_standard_custom_property_propagates_errors(self):
        service = GithubService.__new__(GithubService)
        service.github_client = MagicMock()
        service.github_client.update_repository_custom_properties.side_effect = ValueError(
            "github api failure"
        )

        with self.assertRaises(ValueError):
            service.set_repository_standard_custom_property("test-repo", "standard")


if __name__ == "__main__":
    unittest.main()
