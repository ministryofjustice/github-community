import unittest
from io import BytesIO
from unittest.mock import patch

from app.projects.repository_standards.clients.github_client import GitHubClient
from app.projects.repository_standards.clients.github_client import (
    CoordinatedGithubRetry,
    GitHubRequestCoordinator,
)
from urllib3.response import HTTPResponse
from github import GithubException


class TestCoordinatedGithubRetry(unittest.TestCase):
    def test_rate_limit_cooldown_is_shared_by_retry_clones(self):
        coordinator = unittest.mock.Mock()
        retry = CoordinatedGithubRetry(coordinator, total=3)
        response = HTTPResponse(status=429, headers={"Retry-After": "30"})
        next_retry = retry.increment("GET", "/repos/org/repo", response)
        self.assertIs(next_retry.coordinator, coordinator)
        coordinator.defer.assert_called_once_with(30)
        next_retry.sleep(response)
        coordinator.wait.assert_called_once()

    def test_permission_failure_is_not_retried_as_rate_limiting(self):
        coordinator = unittest.mock.Mock()
        retry = CoordinatedGithubRetry(coordinator, total=3)
        response = HTTPResponse(
            status=403,
            body=BytesIO(b'{"message":"Resource not accessible by integration"}'),
            preload_content=False,
        )
        with self.assertRaises(GithubException):
            retry.increment("GET", "/repos/org/repo", response)
        coordinator.defer.assert_not_called()

    def test_primary_and_secondary_limits_share_cooldown(self):
        for body in (
            b'{"message":"API rate limit exceeded"}',
            b'{"message":"You have exceeded a secondary rate limit"}',
        ):
            with self.subTest(body=body):
                coordinator = unittest.mock.Mock()
                retry = CoordinatedGithubRetry(coordinator, total=3)
                response = HTTPResponse(
                    status=403, body=BytesIO(body), preload_content=False,
                    headers={"X-RateLimit-Reset": "9999999999"},
                )
                next_retry = retry.increment("GET", "/repos/org/repo", response)
                coordinator.defer.assert_called_once()
                self.assertGreaterEqual(coordinator.defer.call_args.args[0], 60)
                next_retry.sleep(response)
                coordinator.wait.assert_called_once()

    def test_wait_does_not_hold_lock_or_shorten_an_existing_cooldown(self):
        coordinator = GitHubRequestCoordinator()
        with (
            patch("app.shared.services.github_app_client.monotonic", side_effect=[0, 0, 0, 30]),
            patch("app.shared.services.github_app_client.sleep") as wait,
        ):
            coordinator.defer(30)
            coordinator.defer(5)
            coordinator.wait()
        wait.assert_called_once_with(30)


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

    def test_secret_alerts_hide_and_discard_secret_values_across_pages(self):
        with patch.object(
            self.client, "_GitHubClient__call",
            side_effect=[
                [{"state": "open", "secret": "never-store-this"}] * 100,
                [{"state": "open", "secret": "also-sensitive"}],
            ],
        ) as request:
            alerts = self.client.get_open_secret_scanning_alerts("example-repo")
        self.assertEqual(alerts, [{"state": "open"}] * 101)
        request.assert_any_call(
            "GET", "/repos/ministryofjustice/example-repo/secret-scanning/alerts",
            params={"state": "open", "per_page": 100, "page": 2, "hide_secret": "true"},
        )

    def test_secret_alert_errors_do_not_expose_response_contents(self):
        with patch.object(
            self.client, "_GitHubClient__call", side_effect=ValueError("sensitive-body")
        ):
            with self.assertRaisesRegex(ValueError, "^Secret Scanning alert data could not be retrieved$"):
                self.client.get_open_secret_scanning_alerts("example-repo")

    def test_gets_open_dependabot_alerts(self):
        response = unittest.mock.Mock(
            ok=True,
            links={},
        )
        response.json.return_value = [{"state": "open"}]
        with (
            patch.object(self.client, "get_token", return_value="token"),
            patch.object(self.client.session, "request", return_value=response) as request,
        ):
            alerts = self.client.get_open_dependabot_alerts("example-repo")

        self.assertEqual(alerts, [{"state": "open"}])
        request.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/ministryofjustice/example-repo/dependabot/alerts",
            params={"state": "open", "per_page": 100},
            timeout=(10, 60),
        )

    def test_follows_dependabot_next_link(self):
        first_response = unittest.mock.Mock(ok=True)
        first_response.json.return_value = [{"number": 1}]
        first_response.links = {
            "next": {
                "url": "https://api.github.com/repos/ministryofjustice/example-repo/dependabot/alerts?after=cursor&per_page=100&state=open"
            }
        }
        second_response = unittest.mock.Mock(ok=True, links={})
        second_response.json.return_value = [{"number": 2}]

        with (
            patch.object(self.client, "get_token", return_value="token"),
            patch.object(
                self.client.session,
                "request",
                side_effect=[first_response, second_response],
            ) as request,
        ):
            alerts = self.client.get_open_dependabot_alerts("example-repo")

        self.assertEqual(alerts, [{"number": 1}, {"number": 2}])
        self.assertEqual(request.call_count, 2)
        request.assert_any_call(
            "GET",
            "https://api.github.com/repos/ministryofjustice/example-repo/dependabot/alerts",
            params={"state": "open", "per_page": 100},
            timeout=(10, 60),
        )
        request.assert_any_call(
            "GET",
            "https://api.github.com/repos/ministryofjustice/example-repo/dependabot/alerts?after=cursor&per_page=100&state=open",
            params=None,
            timeout=(10, 60),
        )


class TestRepositoryLanguages(unittest.TestCase):
    def test_raw_language_response_is_not_augmented_with_url(self):
        client = GitHubClient("client", "key", 123, "ministryofjustice")
        for languages in ({}, {"Python": 1200}):
            with self.subTest(languages=languages):
                response = unittest.mock.Mock(ok=True)
                response.json.return_value = languages
                with (
                    patch.object(client, "get_token", return_value="token"),
                    patch.object(client.session, "request", return_value=response) as request,
                ):
                    result = client.get_repository_languages(".github")
                self.assertEqual(result, languages)
                self.assertNotIn("url", result)
                request.assert_called_once_with(
                    "GET", "https://api.github.com/repos/ministryofjustice/.github/languages",
                    timeout=(10, 60),
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