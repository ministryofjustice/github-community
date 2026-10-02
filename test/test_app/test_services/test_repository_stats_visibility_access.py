import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.projects.repository_stats.services.visibility_access import (
    SESSION_KEY,
    GitHubAccessCheckError,
    is_team_member,
    parse_team,
    resolve_github_username,
    user_has_stats_access,
)

TEAM = "ministryofjustice/repository-stats-viewers"
MEMBERSHIP_PATH = (
    "/orgs/ministryofjustice/teams/repository-stats-viewers/memberships/octocat"
)


def response(status_code, body=None):
    return SimpleNamespace(status_code=status_code, json=lambda: body or {})


class FakeGitHub:
    """Answers GET paths from a dict and records every call."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        result = self.responses.get(path, response(404))
        if isinstance(result, Exception):
            raise result
        return result


def user(nickname="octocat", sub="github|583231"):
    userinfo = {
        "sub": sub,
        "name": "The Octocat",
        "picture": "https://example.test/a.png",
    }
    if nickname is not None:
        userinfo["nickname"] = nickname
    return {"access_token": "x", "expires_at": 9999999999, "userinfo": userinfo}


class TestParseTeam(unittest.TestCase):
    def test_values(self):
        self.assertIsNone(parse_team(None))
        self.assertIsNone(parse_team("  "))
        self.assertEqual(
            parse_team("repository-stats-viewers"),
            ("ministryofjustice", "repository-stats-viewers"),
        )
        self.assertEqual(
            parse_team("moj-analytical-services/viewers"),
            ("moj-analytical-services", "viewers"),
        )


class TestIsTeamMember(unittest.TestCase):
    def test_member(self):
        github = FakeGitHub(
            {MEMBERSHIP_PATH: response(200, {"state": "active", "role": "member"})}
        )
        self.assertTrue(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )
        self.assertEqual(github.calls, [MEMBERSHIP_PATH])

    def test_pending_invitation_is_not_membership(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "pending"})})
        self.assertFalse(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )

    def test_missing_state_fails_closed(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"role": "member"})})
        self.assertFalse(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )

    def test_non_dict_body_fails_closed(self):
        github = FakeGitHub(
            {MEMBERSHIP_PATH: SimpleNamespace(status_code=200, json=lambda: None)}
        )
        self.assertFalse(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )

    def test_non_member(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(404)})
        self.assertFalse(
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        )

    def test_other_status_raises_without_personal_data(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(500)})
        with self.assertRaises(GitHubAccessCheckError) as raised:
            is_team_member(
                "octocat", "ministryofjustice", "repository-stats-viewers", github
            )
        self.assertNotIn("octocat", str(raised.exception))
        self.assertNotIn("repository-stats-viewers", str(raised.exception))


class TestResolveGitHubUsername(unittest.TestCase):
    def test_nickname_first(self):
        lookups = []
        self.assertEqual(resolve_github_username(user(), lookups.append), "octocat")
        self.assertEqual(lookups, [])

    def test_falls_back_to_github_id_in_sub(self):
        self.assertEqual(
            resolve_github_username(
                user(nickname=None), lambda github_id: f"login-for-{github_id}"
            ),
            "login-for-583231",
        )
        self.assertEqual(
            resolve_github_username(user(nickname=" "), lambda github_id: "from-id"),
            "from-id",
        )

    def test_unknown_identity(self):
        lookup = lambda github_id: self.fail("should not look up")
        self.assertIsNone(
            resolve_github_username(user(nickname=None, sub="auth0|abc"), lookup)
        )
        self.assertIsNone(
            resolve_github_username(user(nickname=None, sub=None), lookup)
        )
        self.assertIsNone(resolve_github_username({}, lookup))
        self.assertIsNone(resolve_github_username(None, lookup))

    def test_nickname_is_ignored_without_a_github_sub(self):
        lookup = lambda github_id: self.fail("should not look up")
        for sub in ("auth0|abc", "google-oauth2|123", "github|not-a-number", None):
            with self.subTest(sub=sub):
                self.assertIsNone(
                    resolve_github_username(user(nickname="octocat", sub=sub), lookup)
                )


class TestUserHasStatsAccess(unittest.TestCase):
    def setUp(self):
        patcher = patch(
            "app.projects.repository_stats.services.visibility_access.app_config"
        )
        self.config = patcher.start()
        self.addCleanup(patcher.stop)
        self.config.github.stats_access_team = TEAM

    def test_team_unset_always_allows(self):
        for value in (None, ""):
            with self.subTest(value=value):
                self.config.github.stats_access_team = value
                github = FakeGitHub({})
                cache = {}
                self.assertTrue(user_has_stats_access(None, cache=cache, client=github))
                self.assertTrue(
                    user_has_stats_access(user(), cache=cache, client=github)
                )
                self.assertEqual(github.calls, [])
                self.assertEqual(cache, {})

    def test_member_is_allowed_and_cached(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        cache = {}
        self.assertTrue(user_has_stats_access(user(), cache=cache, client=github))
        self.assertTrue(user_has_stats_access(user(), cache=cache, client=github))
        self.assertEqual(github.calls, [MEMBERSHIP_PATH])
        entry = cache[SESSION_KEY]
        self.assertEqual(
            {k: entry[k] for k in ("username", "has_access", "team", "sub")},
            {
                "username": "octocat",
                "has_access": True,
                "team": TEAM,
                "sub": "github|583231",
            },
        )
        self.assertRegex(entry["checked_at"], r"^\d{4}-\d{2}-\d{2}T")

    def test_non_member_is_denied_and_cached(self):
        github = FakeGitHub({})
        cache = {}
        self.assertFalse(user_has_stats_access(user(), cache=cache, client=github))
        self.assertFalse(user_has_stats_access(user(), cache=cache, client=github))
        self.assertEqual(github.calls, [MEMBERSHIP_PATH])
        self.assertFalse(cache[SESSION_KEY]["has_access"])

    def test_cache_ignored_for_other_user_or_team(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        cache = {
            SESSION_KEY: {
                "sub": "github|1",
                "username": "someone",
                "team": TEAM,
                "has_access": True,
            }
        }
        self.assertTrue(user_has_stats_access(user(), cache=cache, client=github))
        self.assertEqual(len(github.calls), 1)
        self.assertFalse(
            user_has_stats_access(
                user(), team="ministryofjustice/other", cache=cache, client=github
            )
        )
        self.assertEqual(len(github.calls), 2)

    def test_explicit_team_overrides_config(self):
        self.config.github.stats_access_team = None
        path = "/orgs/moj-analytical-services/teams/analysts/memberships/octocat"
        github = FakeGitHub({path: response(200, {"state": "active"})})
        self.assertTrue(
            user_has_stats_access(
                user(), team="moj-analytical-services/analysts", cache={}, client=github
            )
        )
        self.assertEqual(github.calls, [path])

    def test_sub_fallback_looks_up_login_once(self):
        github = FakeGitHub(
            {
                "/user/583231": response(200, {"login": "octocat"}),
                MEMBERSHIP_PATH: response(200, {"state": "active"}),
            }
        )
        cache = {}
        self.assertTrue(
            user_has_stats_access(user(nickname=None), cache=cache, client=github)
        )
        self.assertTrue(
            user_has_stats_access(user(nickname=None), cache=cache, client=github)
        )
        self.assertEqual(github.calls, ["/user/583231", MEMBERSHIP_PATH])

    def test_unresolvable_user_is_denied(self):
        github = FakeGitHub({})
        for session_user in (
            None,
            {},
            user(nickname=None, sub="auth0|abc"),
            user(nickname=None),
        ):
            with self.subTest(session_user=session_user):
                self.assertFalse(
                    user_has_stats_access(session_user, cache={}, client=github)
                )

    def test_errors_deny_are_not_cached_and_log_no_personal_data(self):
        for failure in (
            response(500),
            response(403),
            ConnectionError("down"),
            ValueError("bad key"),
        ):
            with self.subTest(failure=failure):
                github = FakeGitHub({MEMBERSHIP_PATH: failure})
                cache = {}
                with self.assertLogs(
                    "app.projects.repository_stats.services.visibility_access", "DEBUG"
                ) as logs:
                    self.assertFalse(
                        user_has_stats_access(user(), cache=cache, client=github)
                    )
                self.assertEqual(cache, {})
                output = "\n".join(logs.output)
                self.assertNotIn("octocat", output)
                self.assertNotIn("repository-stats-viewers", output)
                self.assertTrue(
                    all(record.levelname == "DEBUG" for record in logs.records)
                )

    def test_uses_flask_session_by_default(self):
        from flask import Flask, session

        app = Flask(__name__)
        app.secret_key = "test"
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        with app.test_request_context():
            self.assertTrue(user_has_stats_access(user(), client=github))
            self.assertTrue(session[SESSION_KEY]["has_access"])


if __name__ == "__main__":
    unittest.main()
