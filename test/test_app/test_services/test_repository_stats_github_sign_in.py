import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests

from app.projects.repository_stats.services import github_sign_in
from app.projects.repository_stats.services.github_sign_in import (
    STATE_SESSION_KEY,
    GitHubSignInError,
    GitHubUnavailableError,
    authorize_url,
    fetch_github_login,
    is_configured,
    safe_next_path,
    take_state_matches,
)

CALLBACK = (
    "https://github-community.service.justice.gov.uk/repository-stats/github/callback"
)
TOKEN = "gho_not-a-real-token"
OAUTH = SimpleNamespace(client_id="client-id", client_secret="client-secret")


def response(status_code, body=None):
    return SimpleNamespace(
        status_code=status_code, ok=status_code < 400, json=lambda: body
    )


class SignInTestCase(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(github_sign_in.app_config.github, "stats_oauth", OAUTH)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestIsConfigured(SignInTestCase):
    def test_needs_both_values(self):
        self.assertTrue(is_configured())
        for oauth in (
            SimpleNamespace(client_id=None, client_secret="x"),
            SimpleNamespace(client_id="x", client_secret=""),
        ):
            with (
                self.subTest(oauth=oauth),
                patch.object(github_sign_in.app_config.github, "stats_oauth", oauth),
            ):
                self.assertFalse(is_configured())


class TestAuthorizeUrl(SignInTestCase):
    def test_url_and_state(self):
        cache = {}
        url = urlsplit(authorize_url(CALLBACK, cache))
        self.assertEqual(
            f"{url.scheme}://{url.netloc}{url.path}",
            "https://github.com/login/oauth/authorize",
        )
        query = parse_qs(url.query)
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["redirect_uri"], [CALLBACK])
        self.assertEqual(query["state"], [cache[STATE_SESSION_KEY]])
        self.assertGreaterEqual(len(cache[STATE_SESSION_KEY]), 40)
        # No permissions asked for.
        self.assertNotIn("scope", query)
        self.assertNotIn("client-secret", url.query)

    def test_new_state_each_time(self):
        cache = {}
        authorize_url(CALLBACK, cache)
        first = cache[STATE_SESSION_KEY]
        authorize_url(CALLBACK, cache)
        self.assertNotEqual(first, cache[STATE_SESSION_KEY])


class TestTakeStateMatches(unittest.TestCase):
    def test_match_is_one_time_use(self):
        cache = {STATE_SESSION_KEY: "abc123"}
        self.assertTrue(take_state_matches("abc123", cache))
        self.assertNotIn(STATE_SESSION_KEY, cache)
        self.assertFalse(take_state_matches("abc123", cache))

    def test_mismatch_missing_or_tampered(self):
        for saved, received in (
            ("abc123", "abc124"),
            ("abc123", None),
            ("abc123", ""),
            (None, "abc123"),
            ("", ""),
        ):
            with self.subTest(saved=saved, received=received):
                cache = {} if saved is None else {STATE_SESSION_KEY: saved}
                self.assertFalse(take_state_matches(received, cache))
                self.assertNotIn(STATE_SESSION_KEY, cache)

    def test_uses_constant_time_compare(self):
        with patch.object(
            github_sign_in.hmac, "compare_digest", return_value=True
        ) as compare:
            self.assertTrue(take_state_matches("x", {STATE_SESSION_KEY: "y"}))
        compare.assert_called_once_with(b"y", b"x")


class TestSafeNextPath(unittest.TestCase):
    def test_safe_paths(self):
        for path, expected in (
            ("/repository-stats/", "/repository-stats/"),
            ("/repository-stats/?", "/repository-stats/"),
            ("/repository-stats/overview?open=a&open=a%2Fb", None),
            ("/repository-stats/visibility?from=2026-01-01", None),
        ):
            with self.subTest(path=path):
                self.assertEqual(safe_next_path(path), expected or path)

    def test_unsafe_paths(self):
        for path in (
            None,
            "",
            "/",
            "/repository-standards/",
            "https://evil.example/repository-stats/",
            "//evil.example/repository-stats/",
            "/repository-stats/..//evil.example",
            "/repository-stats/../auth/logout",
            "/repository-stats/\\evil.example",
            "/repository-stats/\r\nLocation: x",
            "repository-stats/",
            123,
        ):
            with self.subTest(path=path):
                self.assertIsNone(safe_next_path(path))


class TestFetchGitHubLogin(SignInTestCase):
    def fetch(self, token_result, user_result=None):
        def result(value):
            if isinstance(value, Exception):
                raise value
            return value

        with (
            patch.object(
                github_sign_in.requests,
                "post",
                side_effect=lambda *a, **k: result(token_result),
            ) as post,
            patch.object(
                github_sign_in.requests,
                "get",
                side_effect=lambda *a, **k: result(user_result),
            ) as get,
        ):
            try:
                return fetch_github_login("the-code", CALLBACK), post, get
            finally:
                self.post, self.get_ = post, get

    def test_happy_path(self):
        login, post, get = self.fetch(
            response(200, {"access_token": TOKEN, "token_type": "bearer"}),
            response(200, {"login": "octocat", "id": 1}),
        )
        self.assertEqual(login, "octocat")
        post.assert_called_once()
        self.assertEqual(
            post.call_args.args, ("https://github.com/login/oauth/access_token",)
        )
        self.assertEqual(
            post.call_args.kwargs["data"],
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "code": "the-code",
                "redirect_uri": CALLBACK,
            },
        )
        self.assertEqual(
            post.call_args.kwargs["headers"], {"Accept": "application/json"}
        )
        self.assertEqual(post.call_args.kwargs["timeout"], 10)
        self.assertEqual(get.call_args.args, ("https://api.github.com/user",))
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"], f"Bearer {TOKEN}"
        )
        self.assertEqual(get.call_args.kwargs["timeout"], 10)

    def assert_fails(self, error_class, token_result, user_result=None, message=""):
        with self.assertRaises(GitHubSignInError) as raised:
            self.fetch(token_result, user_result)
        self.assertIs(type(raised.exception), error_class)
        text = str(raised.exception)
        self.assertIn(message, text)
        for secret in (TOKEN, "client-secret", "the-code", "octocat"):
            self.assertNotIn(secret, text)
        self.assertIsNone(raised.exception.__cause__)
        return raised.exception

    def test_token_exchange_errors(self):
        self.assert_fails(
            GitHubSignInError,
            response(200, {"error": "bad_verification_code"}),
            message="bad_verification_code",
        )
        self.assert_fails(GitHubSignInError, response(200, {}), message="error: none")
        self.assert_fails(GitHubSignInError, response(200, None))
        self.assert_fails(
            GitHubSignInError,
            response(200, {"error": "Not <safe> to log"}),
            message="none",
        )
        self.assert_fails(
            GitHubSignInError, response(401, {"access_token": TOKEN}), message="401"
        )
        self.assertFalse(self.get_.called)

    def test_token_exchange_unavailable(self):
        for result in (
            response(502),
            requests.ReadTimeout(f"timed out code=the-code {TOKEN}"),
            requests.ConnectionError("down"),
        ):
            with self.subTest(result=result):
                self.assert_fails(GitHubUnavailableError, result)

    def test_user_lookup_errors(self):
        token = response(200, {"access_token": TOKEN})
        self.assert_fails(GitHubSignInError, token, response(401), message="401")
        self.assert_fails(GitHubSignInError, token, response(200, {}))
        self.assert_fails(
            GitHubSignInError, token, response(200, {"login": "bad/login"})
        )
        self.assert_fails(GitHubSignInError, token, response(200, ["octocat"]))

    def test_user_lookup_unavailable(self):
        token = response(200, {"access_token": TOKEN})
        self.assert_fails(GitHubUnavailableError, token, response(503), message="503")
        self.assert_fails(
            GitHubUnavailableError, token, requests.ReadTimeout(f"Bearer {TOKEN}")
        )

    def test_body_that_is_not_json(self):
        def bad_json():
            raise ValueError("not json")

        self.assert_fails(
            GitHubSignInError,
            SimpleNamespace(status_code=200, ok=True, json=bad_json),
        )


if __name__ == "__main__":
    unittest.main()
