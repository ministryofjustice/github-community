import unittest
from types import SimpleNamespace

from app.projects.repository_stats.services.github_inventory import (
    CountingGetter,
    GitHubInventoryError,
)
from app.projects.repository_stats.services.github_teams import (
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
        with self.assertRaisesRegex(GitHubInventoryError, "500"):
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
