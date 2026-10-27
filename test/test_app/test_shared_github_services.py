import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import Mock, patch

import requests
from urllib3 import HTTPSConnectionPool
from urllib3.response import HTTPResponse

from app.shared.services.github_app_client import (
    CoordinatedGitHubAdapter,
    GitHubApiError,
    GitHubAppClient,
    GitHubRequestCoordinator,
    create_installation_token,
)
from app.shared.services.github_collection_config import (
    OrganisationInstallation,
    parse_organisation_installations,
)


MODULE = "app.shared.services.github_app_client"


class TestSharedGitHubAppClient(unittest.TestCase):
    def test_adapter_preserves_permission_body_and_bounds_rate_limit_retries(self):
        for rate_limited, expected_calls in ((False, 1), (True, 4)):
            with self.subTest(rate_limited=rate_limited):
                coordinator = Mock()
                adapter = CoordinatedGitHubAdapter(coordinator)
                self.addCleanup(adapter.close)
                message = (
                    b'{"message":"API rate limit exceeded"}'
                    if rate_limited
                    else b'{"message":"Resource not accessible by integration"}'
                )
                responses = []
                for unused in range(expected_calls):
                    response = requests.Response()
                    response.status_code = 403
                    response._content = message
                    if rate_limited:
                        response.headers["Retry-After"] = "30"
                    responses.append(response)
                request = requests.Request(
                    "GET", "https://api.github.com/orgs/example/repos"
                ).prepare()
                with patch(
                    "requests.adapters.HTTPAdapter.send", side_effect=responses
                ) as send:
                    result = adapter.send(request)
                self.assertEqual(send.call_count, expected_calls)
                self.assertEqual(result.status_code, 403)
                self.assertEqual(result.content, message)
                if rate_limited:
                    self.assertEqual(coordinator.defer.call_count, 3)
                    coordinator.defer.assert_called_with(30)
                else:
                    coordinator.defer.assert_not_called()

    def test_permission_errors_remain_raw_responses_with_retries_enabled(self):
        body = b'{"message":"Resource not accessible by integration"}'
        coordinator = Mock()
        adapter = CoordinatedGitHubAdapter(coordinator)
        pool = HTTPSConnectionPool("api.github.com")
        self.addCleanup(adapter.close)
        self.addCleanup(pool.close)
        forbidden = HTTPResponse(status=403, body=BytesIO(body), preload_content=False)
        with patch.object(pool, "_make_request", return_value=forbidden) as request:
            response = pool.urlopen(
                "GET",
                "/orgs/example/repos",
                retries=adapter.max_retries,
                preload_content=False,
            )
        self.assertEqual(response.status, 403)
        self.assertEqual(response.read(), body)
        request.assert_called_once()
        coordinator.defer.assert_not_called()

    def setUp(self):
        self.client = GitHubAppClient("client", "key", 123)
        self.addCleanup(self.client.close)

    def test_raw_responses_allow_project_specific_error_handling(self):
        response = Mock(ok=False, status_code=403)
        with (
            patch.object(self.client, "get_token", return_value="installation-token"),
            patch.object(
                self.client.session, "request", return_value=response
            ) as request,
        ):
            self.assertIs(
                self.client.get("/orgs/example/repos", params={"page": 2}), response
            )
        request.assert_called_once_with(
            "GET",
            "https://api.github.com/orgs/example/repos",
            params={"page": 2},
            timeout=(10, 60),
        )
        self.assertEqual(
            self.client.session.headers["Authorization"], "Bearer installation-token"
        )
        response.raise_for_status.assert_not_called()

    def test_json_interface_returns_unmodified_payload(self):
        with patch.object(
            self.client, "request", return_value=Mock(ok=True)
        ) as request:
            request.return_value.json.return_value = {}
            self.assertEqual(
                self.client.request_json("GET", "/repos/org/repo/languages"), {}
            )

    def test_json_interface_preserves_status_and_error_message(self):
        response = Mock(ok=False, status_code=404, text="not found")
        response.headers = {
            "X-GitHub-Request-Id": "request-for-support",
            "X-Accepted-GitHub-Permissions": "metadata=read",
        }
        response.json.return_value = {"message": "no analysis found"}
        with patch.object(self.client, "request", return_value=response):
            with self.assertRaises(GitHubApiError) as error:
                self.client.request_json("GET", "/repos/org/repo/code-scanning/alerts")
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.message, "no analysis found")
        self.assertEqual(error.exception.request_id, "request-for-support")
        self.assertEqual(error.exception.accepted_permissions, "metadata=read")

    def test_non_json_errors_keep_the_response_text(self):
        response = Mock(ok=False, status_code=502, text="Bad gateway")
        response.json.side_effect = ValueError("not JSON")
        with patch.object(self.client, "request", return_value=response):
            with self.assertRaisesRegex(GitHubApiError, "Bad gateway"):
                self.client.request_json("GET", "/orgs/example/repos")

    def test_accepts_same_origin_pagination_urls(self):
        url = "https://api.github.com/orgs/example/repos?after=cursor"
        with (
            patch.object(self.client, "get_token", return_value="token"),
            patch.object(self.client.session, "request") as request,
        ):
            self.client.get(url)
        request.assert_called_once_with("GET", url, timeout=(10, 60))

    def test_rejects_foreign_urls_before_authentication_or_request(self):
        for url in (
            "https://example.com/repos",
            "https://api.github.com.example.com/repos",
            "http://api.github.com/repos",
            "//example.com/repos",
            "https://api.github.com@example.com/repos",
        ):
            with (
                self.subTest(url=url),
                patch.object(self.client, "get_token") as token,
                patch.object(self.client.session, "request") as request,
                self.assertRaisesRegex(ValueError, "Refusing to send"),
            ):
                self.client.get(url)
            token.assert_not_called()
            request.assert_not_called()

    def test_tokens_and_sessions_are_isolated_by_installation(self):
        other = GitHubAppClient("client", "key", 456)
        self.addCleanup(other.close)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch(
            f"{MODULE}.create_installation_token",
            side_effect=[
                {"token": "moj-token", "expires_at": expires_at},
                {"token": "mojas-token", "expires_at": expires_at},
            ],
        ) as token:
            self.assertEqual(self.client.get_token(), "moj-token")
            self.assertEqual(other.get_token(), "mojas-token")
            self.assertEqual(self.client.get_token(), "moj-token")
            self.assertEqual(other.get_token(), "mojas-token")
        self.assertEqual([entry.args[2] for entry in token.call_args_list], [123, 456])
        self.assertIsNot(self.client.session, other.session)

    def test_refreshes_tokens_at_actual_expiry_or_after_55_minutes(self):
        for lifetime, refresh_after in ((5, 6), (60, 56)):
            with self.subTest(lifetime=lifetime):
                client = GitHubAppClient("client", "key", 123)
                self.addCleanup(client.close)
                now = datetime.now(timezone.utc)
                with (
                    patch(f"{MODULE}.datetime") as clock,
                    patch(
                        f"{MODULE}.create_installation_token",
                        side_effect=[
                            {
                                "token": "first",
                                "expires_at": now + timedelta(minutes=lifetime),
                            },
                            {"token": "second", "expires_at": now + timedelta(hours=2)},
                        ],
                    ) as token,
                ):
                    clock.now.side_effect = [
                        now,
                        now + timedelta(minutes=1),
                        now + timedelta(minutes=refresh_after),
                    ]
                    self.assertEqual(client.get_token(), "first")
                    self.assertEqual(client.get_token(), "first")
                    self.assertEqual(client.get_token(), "second")
                    self.assertEqual(token.call_count, 2)

    def test_workers_can_share_cooldown_without_sharing_sessions(self):
        coordinator = GitHubRequestCoordinator()
        first = GitHubAppClient("client", "key", 123, request_coordinator=coordinator)
        second = GitHubAppClient("client", "key", 123, request_coordinator=coordinator)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        self.assertIs(first.session.adapters["https://"].coordinator, coordinator)
        self.assertIs(second.session.adapters["https://"].coordinator, coordinator)
        self.assertIsNot(first.session, second.session)

    def test_close_releases_session(self):
        with patch.object(self.client.session, "close") as close:
            self.client.close()
        close.assert_called_once()

    def test_token_creation_uses_installation_endpoint_and_timeout(self):
        response = Mock()
        response.json.return_value = {
            "token": "installation-token",
            "expires_at": "2030-01-01T00:00:00Z",
        }
        with (
            patch(f"{MODULE}.time", return_value=100),
            patch(f"{MODULE}.jwt.encode", return_value="app-jwt") as encode,
            patch(f"{MODULE}.requests.post", return_value=response) as post,
        ):
            result = create_installation_token("client", "key", 456)
        encode.assert_called_once_with(
            {"iat": 100, "exp": 700, "iss": "client"}, "key", algorithm="RS256"
        )
        post.assert_called_once_with(
            "https://api.github.com/app/installations/456/access_tokens",
            headers={
                "Authorization": "Bearer app-jwt",
                "Accept": "application/vnd.github+json",
            },
            timeout=(10, 60),
        )
        response.raise_for_status.assert_called_once()
        self.assertEqual(result["token"], "installation-token")
        self.assertEqual(
            result["expires_at"], datetime(2030, 1, 1, tzinfo=timezone.utc)
        )


class TestSharedOrganisationConfiguration(unittest.TestCase):
    def test_project_selects_its_own_fallback_and_configuration_name(self):
        self.assertEqual(
            parse_organisation_installations(
                None, 456, default_organisation="another-org"
            ),
            [OrganisationInstallation("another-org", 456)],
        )
        with self.assertRaisesRegex(ValueError, "ANOTHER_PROJECT_ORGS"):
            parse_organisation_installations(
                "invalid", 456, configuration_name="ANOTHER_PROJECT_ORGS"
            )

    def test_parses_multiple_installations_without_project_imports(self):
        self.assertEqual(
            parse_organisation_installations(
                "ministryofjustice:123,moj-analytical-services:456", None
            ),
            [
                OrganisationInstallation("ministryofjustice", 123),
                OrganisationInstallation("moj-analytical-services", 456),
            ],
        )
