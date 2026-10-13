import unittest
from types import SimpleNamespace

import requests

from app.projects.repository_stats.services.github_inventory import (
    CountingGetter,
    GitHubInventoryError,
)
from app.projects.repository_stats.services.github_teams import (
    RetryingGetter,
    TeamAccessRecord,
    fetch_org_team_access,
    team_permission,
)

ORG = "example-org"
TEAMS = f"/orgs/{ORG}/teams?per_page=100"


def page(body, next_url=None, status_code=200):
    return SimpleNamespace(
        status_code=status_code,
        json=lambda: body,
        links={"next": {"url": next_url}} if next_url else {},
        headers={},
    )


def team_repos(slug):
    return f"/orgs/{ORG}/teams/{slug}/repos?per_page=100"


class FakeGitHub:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        return self.pages[path]


class TestFetchOrgTeamAccess(unittest.TestCase):
    def test_paginates_teams_and_team_repositories(self):
        teams_2 = "https://api.github.com/organizations/1/teams?per_page=100&page=2"
        repos_2 = "https://api.github.com/teams/1/repos?per_page=100&page=2"
        github = FakeGitHub(
            {
                TEAMS: page(
                    [
                        {
                            "slug": "platform-team",
                            "name": "Platform team",
                            "parent": None,
                        }
                    ],
                    teams_2,
                ),
                teams_2: page(
                    [
                        {
                            "slug": "service-team",
                            "name": "Service team",
                            "parent": {"slug": "platform-team"},
                        }
                    ]
                ),
                team_repos("platform-team"): page(
                    [{"id": 1, "role_name": "admin"}], repos_2
                ),
                repos_2: page([{"id": 2, "role_name": "write"}]),
                team_repos("service-team"): page([{"id": 1, "role_name": "read"}]),
            }
        )
        counting = CountingGetter(github)
        records = fetch_org_team_access(counting, ORG)
        self.assertEqual(
            sorted(records, key=lambda r: (r.github_id, r.team_slug)),
            [
                TeamAccessRecord(
                    ORG, 1, "platform-team", "Platform team", None, "admin"
                ),
                TeamAccessRecord(
                    ORG, 1, "service-team", "Service team", "platform-team", "read"
                ),
                TeamAccessRecord(
                    ORG, 2, "platform-team", "Platform team", None, "write"
                ),
            ],
        )
        self.assertEqual(counting.calls, 5)
        self.assertEqual(len(github.calls), 5)

    def test_a_failed_team_repository_list_fails_the_whole_fetch(self):
        github = FakeGitHub(
            {
                TEAMS: page(
                    [
                        {"slug": "a-team", "name": "A"},
                        {"slug": "b-team", "name": "B"},
                    ]
                ),
                team_repos("a-team"): page([{"id": 1, "role_name": "read"}]),
                team_repos("b-team"): page(
                    {"message": "Server Error"}, status_code=500
                ),
            }
        )
        sleeps = []
        with (
            self.assertLogs(
                "app.projects.repository_stats.services.github_teams", "WARNING"
            ),
            self.assertRaisesRegex(GitHubInventoryError, "500"),
        ):
            fetch_org_team_access(github, ORG, sleep=sleeps.append)
        self.assertEqual(github.calls.count(team_repos("b-team")), 3)
        self.assertEqual(sleeps, [2, 5])

    def test_a_404_on_one_team_skips_only_that_team(self):
        github = FakeGitHub(
            {
                TEAMS: page(
                    [
                        {"slug": "a-team", "name": "A"},
                        {"slug": "gone-team", "name": "Gone"},
                        {"slug": "c-team", "name": "C"},
                    ]
                ),
                team_repos("a-team"): page([{"id": 1, "role_name": "read"}]),
                team_repos("gone-team"): page(
                    {"message": "Not Found"}, status_code=404
                ),
                team_repos("c-team"): page([{"id": 3, "role_name": "admin"}]),
            }
        )
        sleeps = []
        with self.assertLogs(
            "app.projects.repository_stats.services.github_teams", "WARNING"
        ) as logs:
            records = fetch_org_team_access(github, ORG, sleep=sleeps.append)
        self.assertEqual(
            sorted((r.github_id, r.team_slug) for r in records),
            [(1, "a-team"), (3, "c-team")],
        )
        self.assertEqual(len(logs.output), 1)
        self.assertIn("gone-team", logs.output[0])
        self.assertIn("404", logs.output[0])
        # 404s aren't retried.
        self.assertEqual(github.calls.count(team_repos("gone-team")), 1)
        self.assertEqual(sleeps, [])

    def test_a_404_on_the_team_list_still_fails_the_fetch(self):
        github = FakeGitHub({TEAMS: page({"message": "Not Found"}, status_code=404)})
        with self.assertRaisesRegex(GitHubInventoryError, "404"):
            fetch_org_team_access(github, ORG)

    def test_other_4xx_on_a_team_still_fails_the_fetch(self):
        github = FakeGitHub(
            {
                TEAMS: page([{"slug": "a-team"}, {"slug": "b-team"}]),
                team_repos("a-team"): page({"message": "Forbidden"}, status_code=403),
                team_repos("b-team"): page([{"id": 2, "role_name": "read"}]),
            }
        )
        with self.assertRaisesRegex(GitHubInventoryError, "403"):
            fetch_org_team_access(github, ORG)

    def test_unexpected_body_and_missing_slug(self):
        with self.assertRaisesRegex(GitHubInventoryError, "unexpected team list"):
            fetch_org_team_access(FakeGitHub({TEAMS: page({"oops": 1})}), ORG)
        with self.assertRaisesRegex(GitHubInventoryError, "without a slug"):
            fetch_org_team_access(FakeGitHub({TEAMS: page([{"name": "x"}])}), ORG)

    def test_no_teams(self):
        github = FakeGitHub({TEAMS: page([])})
        self.assertEqual(fetch_org_team_access(github, ORG), [])
        self.assertEqual(github.calls, [TEAMS])

    def test_slug_is_quoted_in_the_path(self):
        github = FakeGitHub(
            {
                TEAMS: page([{"slug": "odd/slug", "name": "Odd"}]),
                f"/orgs/{ORG}/teams/odd%2Fslug/repos?per_page=100": page([]),
            }
        )
        self.assertEqual(fetch_org_team_access(github, ORG), [])


class Flaky:
    """Returns (or raises) each outcome in turn, one per call."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, path):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestRetryingGetter(unittest.TestCase):
    def setUp(self):
        self.sleeps = []

    def getter(self, *outcomes):
        self.flaky = Flaky(*outcomes)
        return RetryingGetter(self.flaky, sleep=self.sleeps.append)

    def test_success_first_time_does_not_retry(self):
        ok = page([])
        self.assertIs(self.getter(ok).get("/x"), ok)
        self.assertEqual((self.flaky.calls, self.sleeps), (1, []))

    def test_read_timeout_then_success(self):
        ok = page([])
        with self.assertLogs(
            "app.projects.repository_stats.services.github_teams", "WARNING"
        ) as logs:
            response = self.getter(requests.ReadTimeout("slow"), ok).get("/x")
        self.assertIs(response, ok)
        self.assertEqual((self.flaky.calls, self.sleeps), (2, [2]))
        self.assertIn("ReadTimeout", logs.output[0])
        self.assertIn("attempt 2 of 3", logs.output[0])

    def test_connection_error_and_5xx_are_retried(self):
        ok = page([])
        with self.assertLogs("app.projects.repository_stats.services.github_teams"):
            response = self.getter(
                requests.ConnectionError("reset"), page({}, status_code=502), ok
            ).get("/x")
        self.assertIs(response, ok)
        self.assertEqual((self.flaky.calls, self.sleeps), (3, [2, 5]))

    def test_gives_up_after_three_timeouts(self):
        with (
            self.assertLogs("app.projects.repository_stats.services.github_teams"),
            self.assertRaises(requests.ReadTimeout),
        ):
            self.getter(*[requests.ReadTimeout("slow")] * 3).get("/x")
        self.assertEqual((self.flaky.calls, self.sleeps), (3, [2, 5]))

    def test_returns_last_5xx_after_three_attempts(self):
        last = page({}, status_code=503)
        with self.assertLogs("app.projects.repository_stats.services.github_teams"):
            response = self.getter(
                page({}, status_code=500), page({}, status_code=500), last
            ).get("/x")
        self.assertIs(response, last)
        self.assertEqual(self.flaky.calls, 3)

    def test_4xx_is_not_retried(self):
        forbidden = page({}, status_code=403)
        self.assertIs(self.getter(forbidden).get("/x"), forbidden)
        self.assertEqual((self.flaky.calls, self.sleeps), (1, []))

    def test_other_errors_are_not_retried(self):
        with self.assertRaises(ValueError):
            self.getter(ValueError("bug")).get("/x")
        self.assertEqual(self.flaky.calls, 1)

    def test_log_does_not_include_the_path(self):
        with self.assertLogs(
            "app.projects.repository_stats.services.github_teams"
        ) as logs:
            self.getter(requests.ReadTimeout("slow"), page([])).get(
                "/orgs/o/teams/secret-team/repos"
            )
        self.assertNotIn("secret-team", "\n".join(logs.output))

    def test_one_timeout_on_a_team_call_keeps_the_team_data(self):
        github = FakeGitHub(
            {
                TEAMS: page([{"slug": "a-team"}, {"slug": "b-team"}]),
                team_repos("a-team"): page([{"id": 1, "role_name": "read"}]),
                team_repos("b-team"): page([{"id": 2, "role_name": "admin"}]),
            }
        )
        original = github.get
        timed_out = []

        def get(path):
            if path == team_repos("b-team") and not timed_out:
                timed_out.append(path)
                raise requests.ReadTimeout("Read timed out. (read timeout=10)")
            return original(path)

        github.get = get
        with self.assertLogs("app.projects.repository_stats.services.github_teams"):
            records = fetch_org_team_access(github, ORG, sleep=self.sleeps.append)
        self.assertEqual(
            sorted((r.github_id, r.team_slug) for r in records),
            [(1, "a-team"), (2, "b-team")],
        )
        self.assertEqual(self.sleeps, [2])


class TestTeamPermission(unittest.TestCase):
    def test_role_name_wins(self):
        self.assertEqual(
            team_permission(
                {"role_name": "custom-role", "permissions": {"admin": True}}
            ),
            "custom-role",
        )

    def test_falls_back_to_highest_permission(self):
        self.assertEqual(
            team_permission({"permissions": {"pull": True, "push": True}}), "write"
        )
        self.assertEqual(team_permission({"permissions": {"pull": True}}), "read")
        self.assertEqual(team_permission({}), "unknown")


if __name__ == "__main__":
    unittest.main()
