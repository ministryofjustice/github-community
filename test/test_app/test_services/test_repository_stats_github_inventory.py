# ruff: noqa: DTZ001 - naive datetimes here are UTC, as stored by the database
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.projects.repository_stats.clients.github_client import GitHubAppClient
from app.projects.repository_stats.config.collection_config import (
    OrgInstallation,
    parse_org_installations,
)
from app.projects.repository_stats.services.github_inventory import (
    GitHubInventoryError,
    OrganisationProfile,
    RepositoryRecord,
    fetch_org_profile,
    fetch_org_repositories,
    parse_github_datetime,
)
from app.projects.repository_stats.services.uk_time import (
    _UkFallback,
    format_last_updated,
    london_date,
)

FIRST_PAGE = "/orgs/ministryofjustice/repos?type=all&per_page=100"


def repo(
    github_id,
    name,
    visibility="public",
    archived=False,
    fork=False,
    pushed_at="2026-09-01T10:00:00Z",
):
    return {
        "id": github_id,
        "name": name,
        "full_name": f"ministryofjustice/{name}",
        "visibility": visibility,
        "private": visibility != "public",
        "archived": archived,
        "fork": fork,
        "created_at": "2020-01-02T03:04:05Z",
        "pushed_at": pushed_at,
        "owner": {"login": "ministryofjustice"},
    }


def page(body, next_url=None, status_code=200, headers=None):
    return SimpleNamespace(
        status_code=status_code,
        json=lambda: body,
        links={"next": {"url": next_url}} if next_url else {},
        headers=headers or {},
    )


class FakeGitHub:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        return self.pages[path]


class TestFetchOrgRepositories(unittest.TestCase):
    def test_follows_pagination_and_maps_fields(self):
        second = (
            "https://api.github.com/organizations/1/repos?type=all&per_page=100&page=2"
        )
        github = FakeGitHub(
            {
                FIRST_PAGE: page(
                    [repo(1, "one"), repo(2, "two", "internal", archived=True)], second
                ),
                second: page([repo(3, "three", "private", fork=True, pushed_at=None)]),
            }
        )
        records = fetch_org_repositories(github, "ministryofjustice")
        self.assertEqual(github.calls, [FIRST_PAGE, second])
        self.assertEqual(
            records,
            [
                RepositoryRecord(
                    1,
                    "ministryofjustice",
                    "one",
                    "public",
                    False,
                    False,
                    datetime(2020, 1, 2, 3, 4, 5),
                    datetime(2026, 9, 1, 10),
                ),
                RepositoryRecord(
                    2,
                    "ministryofjustice",
                    "two",
                    "internal",
                    True,
                    False,
                    datetime(2020, 1, 2, 3, 4, 5),
                    datetime(2026, 9, 1, 10),
                ),
                RepositoryRecord(
                    3,
                    "ministryofjustice",
                    "three",
                    "private",
                    False,
                    True,
                    datetime(2020, 1, 2, 3, 4, 5),
                    None,
                ),
            ],
        )

    def test_requests_every_type_100_per_page(self):
        self.assertIn("type=all", FIRST_PAGE)
        self.assertIn("per_page=100", FIRST_PAGE)

    def test_empty_organisation(self):
        self.assertEqual(
            fetch_org_repositories(
                FakeGitHub({FIRST_PAGE: page([])}), "ministryofjustice"
            ),
            [],
        )

    def test_visibility_falls_back_to_private_flag(self):
        data = repo(1, "old")
        del data["visibility"]
        data["private"] = True
        records = fetch_org_repositories(
            FakeGitHub({FIRST_PAGE: page([data])}), "ministryofjustice"
        )
        self.assertEqual(records[0].visibility, "private")

    def test_error_on_a_later_page_fails_the_whole_fetch(self):
        second = "https://api.github.com/next"
        github = FakeGitHub(
            {
                FIRST_PAGE: page([repo(1, "one")], second),
                second: page({}, status_code=502),
            }
        )
        with self.assertRaisesRegex(GitHubInventoryError, "status 502"):
            fetch_org_repositories(github, "ministryofjustice")

    def test_rate_limit(self):
        for headers, status in (
            ({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1790000000"}, 403),
            ({"retry-after": "60"}, 429),
        ):
            with self.subTest(headers=headers):
                github = FakeGitHub(
                    {
                        FIRST_PAGE: page(
                            {"message": "rate limit"},
                            status_code=status,
                            headers=headers,
                        )
                    }
                )
                with self.assertRaisesRegex(GitHubInventoryError, "rate limit"):
                    fetch_org_repositories(github, "ministryofjustice")

    def test_not_found_and_unexpected_body(self):
        with self.assertRaisesRegex(GitHubInventoryError, "status 404"):
            fetch_org_repositories(
                FakeGitHub({FIRST_PAGE: page({}, status_code=404)}), "ministryofjustice"
            )
        with self.assertRaisesRegex(GitHubInventoryError, "unexpected"):
            fetch_org_repositories(
                FakeGitHub({FIRST_PAGE: page({"oops": 1})}), "ministryofjustice"
            )

    def test_endless_pagination_is_stopped(self):
        github = FakeGitHub({FIRST_PAGE: page([repo(1, "one")], FIRST_PAGE)})
        with (
            patch(
                "app.projects.repository_stats.services.github_inventory.MAX_PAGES", 3
            ),
            self.assertRaisesRegex(GitHubInventoryError, "pagination"),
        ):
            fetch_org_repositories(github, "ministryofjustice")
        self.assertEqual(len(github.calls), 3)

    def test_parse_github_datetime(self):
        self.assertIsNone(parse_github_datetime(None))
        self.assertEqual(
            parse_github_datetime("2026-03-29T00:30:00Z"), datetime(2026, 3, 29, 0, 30)
        )


class TestFetchOrgProfile(unittest.TestCase):
    PATH = "/orgs/example-org"

    def test_display_name(self):
        github = FakeGitHub({self.PATH: page({"login": "example-org", "name": " Ex "})})
        self.assertEqual(
            fetch_org_profile(github, "example-org"),
            OrganisationProfile("example-org", "Ex"),
        )
        self.assertEqual(github.calls, [self.PATH])

    def test_missing_or_blank_name(self):
        for body in ({"login": "example-org"}, {"name": None}, {"name": "  "}):
            with self.subTest(body=body):
                profile = fetch_org_profile(
                    FakeGitHub({self.PATH: page(body)}), "example-org"
                )
                self.assertIsNone(profile.display_name)

    def test_errors_raise(self):
        for response in (page({}, status_code=404), page(["not", "a", "dict"])):
            with (
                self.subTest(status=response.status_code),
                self.assertRaises(GitHubInventoryError),
            ):
                fetch_org_profile(FakeGitHub({self.PATH: response}), "example-org")


class TestGitHubAppClientUrls(unittest.TestCase):
    def setUp(self):
        self.client = GitHubAppClient("app", "key", 1)
        token = patch.object(
            GitHubAppClient, "_GitHubAppClient__get_token", return_value="t"
        )
        token.start()
        self.addCleanup(token.stop)

    def test_paths_and_github_next_links(self):
        with patch(
            "app.projects.repository_stats.clients.github_client.requests.get"
        ) as get:
            self.client.get("/orgs/x/repos")
            self.client.get("https://api.github.com/organizations/1/repos?page=2")
        self.assertEqual(
            [c.args[0] for c in get.call_args_list],
            [
                "https://api.github.com/orgs/x/repos",
                "https://api.github.com/organizations/1/repos?page=2",
            ],
        )

    def test_never_sends_the_token_elsewhere(self):
        with patch(
            "app.projects.repository_stats.clients.github_client.requests.get"
        ) as get:
            for url in (
                "https://evil.example/repos",
                "https://api.github.com.evil.example/x",
                "http://api.github.com/x",
            ):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    self.client.get(url)
        get.assert_not_called()


class TestOrgInstallations(unittest.TestCase):
    def test_default_is_ministryofjustice_with_the_app_installation(self):
        self.assertEqual(
            parse_org_installations(None, 123),
            [OrgInstallation("ministryofjustice", 123)],
        )
        self.assertEqual(
            parse_org_installations("  ", 123),
            [OrgInstallation("ministryofjustice", 123)],
        )

    def test_more_organisations_are_config_only(self):
        self.assertEqual(
            parse_org_installations(
                "ministryofjustice:1, moj-analytical-services:2", 999
            ),
            [
                OrgInstallation("ministryofjustice", 1),
                OrgInstallation("moj-analytical-services", 2),
            ],
        )

    def test_invalid(self):
        for value, default in (
            ("", 0),
            (None, None),
            ("ministryofjustice", 1),
            ("a:x", 1),
            (":1", 1),
            ("a:1,a:2", 1),
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_org_installations(value, default)


class TestUkTime(unittest.TestCase):
    def test_format_last_updated(self):
        cases = (
            (
                datetime(2026, 9, 25, 12, 4, tzinfo=UTC),
                ("25 September 2026", "1:04pm"),
            ),  # BST
            (
                datetime(2026, 1, 5, 13, 4, tzinfo=UTC),
                ("5 January 2026", "1:04pm"),
            ),  # GMT
            (datetime(2026, 9, 25, 12, 4), ("25 September 2026", "1:04pm")),
            (
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                ("1 January 2026", "12:00am"),
            ),  # midnight
            (
                datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
                ("1 January 2026", "12:00pm"),
            ),  # midday
            (
                datetime(2026, 6, 30, 23, 30, tzinfo=UTC),
                ("1 July 2026", "12:30am"),
            ),  # BST moves the date
            (datetime(2026, 6, 30, 11, 59, tzinfo=UTC), ("30 June 2026", "12:59pm")),
            (datetime(2026, 2, 3, 9, 7, tzinfo=UTC), ("3 February 2026", "9:07am")),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_last_updated(value), expected)
        self.assertIsNone(format_last_updated(None))

    def test_london_date_for_the_job(self):
        self.assertEqual(
            london_date(datetime(2026, 6, 30, 23, 30, tzinfo=UTC)).isoformat(),
            "2026-07-01",
        )
        self.assertEqual(
            london_date(datetime(2026, 12, 31, 23, 30, tzinfo=UTC)).isoformat(),
            "2026-12-31",
        )

    def test_fallback_matches_the_tz_database(self):
        fallback, london = _UkFallback(), ZoneInfo("Europe/London")
        for year in (2025, 2026, 2027):
            start = datetime(year, 1, 1, tzinfo=UTC)
            for hours in range(0, 366 * 24, 7):
                value = start + timedelta(hours=hours)
                self.assertEqual(
                    value.astimezone(fallback).replace(tzinfo=None),
                    value.astimezone(london).replace(tzinfo=None),
                    value,
                )
        for edge in (
            datetime(2026, 3, 29, 0, 59, tzinfo=UTC),
            datetime(2026, 3, 29, 1, 0, tzinfo=UTC),
            datetime(2026, 10, 25, 0, 59, tzinfo=UTC),
            datetime(2026, 10, 25, 1, 0, tzinfo=UTC),
        ):
            self.assertEqual(
                edge.astimezone(fallback).hour, edge.astimezone(london).hour, edge
            )


if __name__ == "__main__":
    unittest.main()
