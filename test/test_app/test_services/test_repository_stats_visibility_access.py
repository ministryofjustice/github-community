import logging
import unittest
from types import SimpleNamespace

from app.projects.repository_stats.services.visibility_access import (
    ACCESS_RECHECK_SECONDS,
    GITHUB_SESSION_KEY,
    SESSION_KEY,
    GitHubAccessCheckError,
    StatsAccess,
    check_stats_access,
    clear_github_sign_in,
    get_github_login,
    is_team_member,
    parse_team,
    remember_github_login,
)

TEAM = "ministryofjustice/repository-stats-viewers"
MEMBERSHIP_PATH = (
    "/orgs/ministryofjustice/teams/repository-stats-viewers/memberships/octocat"
)
NOW = 1_800_000_000.0


def response(status_code, body=None):
    return SimpleNamespace(status_code=status_code, json=lambda: body or {})


class FakeGitHub:
    """Answers GET paths from a dict; records every call."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        result = self.responses.get(path, response(404))
        if isinstance(result, Exception):
            raise result
        return result


def microsoft_user(sub="waad|pairwise-id"):
    return {
        "access_token": "x",
        "expires_at": 9999999999,
        "userinfo": {"sub": sub, "nickname": "octo.cat", "name": "Octo Cat"},
    }


def signed_in_cache(login="octocat", user=None):
    cache = {}
    remember_github_login(user or microsoft_user(), login, cache, now=lambda: NOW)
    return cache


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


class TestGitHubLoginInSession(unittest.TestCase):
    def test_remember_and_read(self):
        cache = signed_in_cache()
        self.assertEqual(
            cache[GITHUB_SESSION_KEY],
            {"login": "octocat", "auth_sub": "waad|pairwise-id", "signed_in_at": NOW},
        )
        self.assertEqual(get_github_login(microsoft_user(), cache), "octocat")

    def test_no_github_sign_in(self):
        self.assertIsNone(get_github_login(microsoft_user(), {}))

    def test_github_login_for_another_microsoft_user_is_ignored_and_cleared(self):
        cache = signed_in_cache()
        cache[SESSION_KEY] = {TEAM: {"login": "octocat", "has_access": True}}
        self.assertIsNone(get_github_login(microsoft_user("waad|someone-else"), cache))
        self.assertNotIn(GITHUB_SESSION_KEY, cache)
        self.assertNotIn(SESSION_KEY, cache)

    def test_remembering_a_new_login_drops_old_team_results(self):
        cache = signed_in_cache()
        cache[SESSION_KEY] = {TEAM: {"login": "octocat", "has_access": True}}
        remember_github_login(microsoft_user(), "hubot", cache)
        self.assertNotIn(SESSION_KEY, cache)
        self.assertEqual(get_github_login(microsoft_user(), cache), "hubot")

    def test_clear_keeps_the_microsoft_sign_in(self):
        cache = signed_in_cache()
        cache["user"] = microsoft_user()
        cache[SESSION_KEY] = {}
        clear_github_sign_in(cache)
        self.assertEqual(list(cache), ["user"])


class TestCheckStatsAccess(unittest.TestCase):
    def check(self, cache, github=None, now=NOW, team=TEAM, user=None):
        return check_stats_access(
            user or microsoft_user(),
            team=team,
            cache=cache,
            client=github or FakeGitHub({}),
            now=lambda: now,
        )

    def test_team_unset_always_allows_without_github_sign_in(self):
        github = FakeGitHub({})
        for team in ("", "  "):
            with self.subTest(team=team):
                self.assertIs(self.check({}, github, team=team), StatsAccess.ALLOWED)
        self.assertEqual(github.calls, [])

    def test_team_unset_in_config_allows(self):
        from unittest.mock import patch

        with patch(
            "app.projects.repository_stats.services.visibility_access.app_config.github.stats_access_team",
            None,
        ):
            self.assertIs(
                check_stats_access(microsoft_user(), cache={}), StatsAccess.ALLOWED
            )

    def test_needs_github_sign_in_first(self):
        github = FakeGitHub({})
        self.assertIs(self.check({}, github), StatsAccess.NEEDS_GITHUB)
        self.assertEqual(github.calls, [])

    def test_member_is_allowed_and_cached(self):
        cache = signed_in_cache()
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        self.assertIs(self.check(cache, github), StatsAccess.ALLOWED)
        self.assertEqual(
            cache[SESSION_KEY],
            {TEAM: {"login": "octocat", "has_access": True, "checked_at": NOW}},
        )
        self.assertIs(self.check(cache, github, now=NOW + 60), StatsAccess.ALLOWED)
        self.assertEqual(github.calls, [MEMBERSHIP_PATH])

    def test_non_member_is_denied_and_cached(self):
        cache = signed_in_cache()
        github = FakeGitHub({MEMBERSHIP_PATH: response(404)})
        self.assertIs(self.check(cache, github), StatsAccess.DENIED)
        self.assertIs(self.check(cache, github), StatsAccess.DENIED)
        self.assertEqual(github.calls, [MEMBERSHIP_PATH])

    def test_rechecked_once_the_cache_is_an_hour_old(self):
        cache = signed_in_cache()
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        self.assertIs(self.check(cache, github), StatsAccess.ALLOWED)
        later = NOW + ACCESS_RECHECK_SECONDS - 1
        self.assertIs(self.check(cache, github, now=later), StatsAccess.ALLOWED)
        self.assertEqual(len(github.calls), 1)
        # Removed from the team: the next hourly check denies, with no new GitHub
        # sign-in needed.
        github.responses[MEMBERSHIP_PATH] = response(404)
        an_hour_later = NOW + ACCESS_RECHECK_SECONDS
        self.assertIs(self.check(cache, github, now=an_hour_later), StatsAccess.DENIED)
        self.assertEqual(len(github.calls), 2)
        self.assertEqual(cache[SESSION_KEY][TEAM]["checked_at"], an_hour_later)

    def test_cache_from_the_future_is_rechecked(self):
        cache = signed_in_cache()
        cache[SESSION_KEY] = {
            TEAM: {"login": "octocat", "has_access": True, "checked_at": NOW + 999}
        }
        github = FakeGitHub({MEMBERSHIP_PATH: response(404)})
        self.assertIs(self.check(cache, github), StatsAccess.DENIED)

    def test_new_session_is_always_checked(self):
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        for _ in range(2):
            self.assertIs(self.check(signed_in_cache(), github), StatsAccess.ALLOWED)
        self.assertEqual(len(github.calls), 2)

    def test_cache_ignored_for_other_login_or_team(self):
        cache = signed_in_cache()
        cache[SESSION_KEY] = {
            TEAM: {"login": "someone-else", "has_access": True, "checked_at": NOW},
            "ministryofjustice/other": {
                "login": "octocat",
                "has_access": True,
                "checked_at": NOW,
            },
        }
        github = FakeGitHub({MEMBERSHIP_PATH: response(404)})
        self.assertIs(self.check(cache, github), StatsAccess.DENIED)
        self.assertEqual(github.calls, [MEMBERSHIP_PATH])
        # Results for other teams are kept.
        self.assertIn("ministryofjustice/other", cache[SESSION_KEY])

    def test_malformed_cache_is_rechecked(self):
        for bad in ("yes", {TEAM: "yes"}, {TEAM: {"login": "octocat"}}):
            with self.subTest(bad=bad):
                cache = signed_in_cache()
                cache[SESSION_KEY] = bad
                github = FakeGitHub({MEMBERSHIP_PATH: response(404)})
                self.assertIs(self.check(cache, github), StatsAccess.DENIED)
                self.assertEqual(github.calls, [MEMBERSHIP_PATH])

    def test_explicit_team_overrides_config(self):
        cache = signed_in_cache()
        path = "/orgs/other-org/teams/viewers/memberships/octocat"
        github = FakeGitHub({path: response(200, {"state": "active"})})
        self.assertIs(
            self.check(cache, github, team="other-org/viewers"), StatsAccess.ALLOWED
        )
        self.assertEqual(github.calls, [path])

    def test_errors_fail_closed_are_not_cached_and_log_no_personal_data(self):
        for error in (
            response(500),
            response(403),
            ConnectionError("https://api.github.com/.../memberships/octocat"),
        ):
            with self.subTest(error=error):
                cache = signed_in_cache()
                github = FakeGitHub({MEMBERSHIP_PATH: error})
                with self.assertLogs(
                    "app.projects.repository_stats.services.visibility_access",
                    logging.WARNING,
                ) as logs:
                    self.assertIs(self.check(cache, github), StatsAccess.UNAVAILABLE)
                self.assertNotIn(SESSION_KEY, cache)
                output = "\n".join(logs.output)
                self.assertNotIn("octocat", output)
                self.assertNotIn("repository-stats-viewers", output)
                # The next request asks GitHub again.
                github.responses[MEMBERSHIP_PATH] = response(200, {"state": "active"})
                self.assertIs(self.check(cache, github), StatsAccess.ALLOWED)

    def test_uses_flask_session_by_default(self):
        from flask import Flask, session

        app = Flask(__name__)
        app.secret_key = "test"
        github = FakeGitHub({MEMBERSHIP_PATH: response(200, {"state": "active"})})
        with app.test_request_context():
            remember_github_login(microsoft_user(), "octocat")
            self.assertIs(
                check_stats_access(microsoft_user(), team=TEAM, client=github),
                StatsAccess.ALLOWED,
            )
            self.assertTrue(session[SESSION_KEY][TEAM]["has_access"])


if __name__ == "__main__":
    unittest.main()
