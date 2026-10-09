import csv
import io
import json
import os
import re
import time
import unittest
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

import requests
from flask import Flask

from app.projects.repository_stats.config.visibility_config import (
    VISIBILITY_HISTORY_START_DATE,
    VISIBILITY_SLACK_CHANNEL_NAME,
    VISIBILITY_SLACK_CHANNEL_URL,
)
from app.projects.repository_stats.routes.main import repository_stats_main
from app.projects.repository_stats.services.business_units import (
    RepositoryBusinessUnits,
)
from app.projects.repository_stats.services.overview_logic import RepositoryTeams, Team
from app.projects.repository_stats.services.visibility_access import (
    GITHUB_SESSION_KEY,
    SESSION_KEY,
    GitHubAccessCheckError,
)
from app.projects.repository_stats.services.visibility_logic import (
    VisibilityEvent,
    VisibilitySnapshot,
)
from app.projects.repository_stats.services.visibility_service import (
    VisibilityService,
)
from app.shared.config.jinja_config import configure_jinja
from app.shared.routes.main import main

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "app")
ORG = "ministryofjustice"
OTHER_ORG = "moj-analytical-services"
AUG_1 = date(2026, 8, 1)
SEP_25 = date(2026, 9, 25)
CHANGES_URL = "/repository-stats/visibility"
ARCHIVED_URL = "/repository-stats/archived"
OVERVIEW_URL = "/repository-stats/overview"
TODAY = date(2026, 10, 1)  # a week after the latest stub snapshot
NO_HEADING = '<h2 class="govuk-heading-m">Last updated'
LAST_UPDATED_LINE = (
    '<p class="govuk-body-s">Last updated: 25 September 2026 at <em>1:04pm</em></p>'
)


def snap(github_id, name, visibility, captured_on, archived=False, fork=False, org=ORG):
    return VisibilitySnapshot(
        github_id,
        org,
        name,
        visibility,
        archived,
        captured_on,
        fork,
        pushed_at=datetime(2023, 5, 6, 12, 0),  # noqa: DTZ001
    )


def change(github_id, name, from_v, to_v, day, event_type="changed"):
    return VisibilityEvent(github_id, ORG, name, event_type, day, "scan", from_v, to_v)


class FakeVisibilityRepository:
    """31 visibility changes, 1 new and 1 deleted repository, archived repositories and
    one repository in a second organisation."""

    def __init__(self):
        self.snapshots = {AUG_1: [], SEP_25: []}
        self.events = []
        for i in range(30):
            name = f"sample-repo-{i:02d}"
            self.snapshots[AUG_1].append(snap(i, name, "public", AUG_1))
            self.snapshots[SEP_25].append(snap(i, name, "internal", SEP_25))
            self.events.append(
                change(i, name, "public", "internal", AUG_1 + timedelta(days=1 + i))
            )
        self.snapshots[SEP_25].append(snap(100, "sample-new", "public", SEP_25))
        self.events.append(
            change(100, "sample-new", None, "public", date(2026, 9, 10), "created")
        )
        self.snapshots[AUG_1].append(snap(101, "=cmd|evil", "private", AUG_1))
        self.events.append(
            change(101, "=cmd|evil", "private", None, date(2026, 9, 11), "deleted")
        )
        for github_id, name, now in (
            (200, "asset-alpha", "public"),
            (201, "sample-archived-moved", "internal"),
        ):
            self.snapshots[AUG_1].append(
                snap(github_id, name, "public", AUG_1, archived=True)
            )
            self.snapshots[SEP_25].append(
                snap(github_id, name, now, SEP_25, archived=True, fork=github_id == 201)
            )
        self.events.append(
            change(
                201, "sample-archived-moved", "public", "internal", date(2026, 9, 12)
            )
        )
        for captured_on in (AUG_1, SEP_25):
            self.snapshots[captured_on].append(
                snap(300, "mas-model", "public", captured_on, org=OTHER_ORG)
            )

    def find_snapshot_dates(self):
        return sorted(self.snapshots)

    def find_snapshots_on_dates(self, dates):
        return {d: self.snapshots.get(d, []) for d in dates}

    def find_events_between(self, from_date, to_date):
        return [e for e in self.events if from_date <= e.occurred_on <= to_date]

    def find_first_archived_dates(self):
        return {200: AUG_1, 201: AUG_1}

    def find_organisations(self):
        return [ORG, OTHER_ORG]

    display_names: Mapping[str, str] = MappingProxyType({})

    def find_organisation_display_names(self):
        return dict(self.display_names)

    last_run_finished_at = datetime(2026, 9, 25, 12, 4)  # noqa: DTZ001 - stored as UTC, 1:04pm BST

    def find_last_successful_run_finished_at(self, job_name):
        assert job_name == "record_repository_visibility"
        return self.last_run_finished_at

    imported_events = False

    def has_events_from_source(self, source):
        assert source == "import"
        return self.imported_events


class EmptyVisibilityRepository(FakeVisibilityRepository):
    def __init__(self):
        self.snapshots = {}
        self.events = []

    def find_first_archived_dates(self):
        return {}

    def find_organisations(self):
        return []

    last_run_finished_at = None


def teams_by_name(slugs_by_name):
    return RepositoryTeams(
        by_name={
            name: [Team(slug, slug) for slug in slugs]
            for name, slugs in slugs_by_name.items()
        }
    )


class FakeOwnership:
    def business_unit_names(self):
        return ["HMPPS", "Office of the CTO"]

    def business_units_by_repository(self):
        return {"asset-alpha": ["Office of the CTO"], "sample-repo-00": ["HMPPS"]}

    def teams_by_repository(self):
        return teams_by_name(
            {
                "asset-alpha": ["service-team", "platform-team"],
                "sample-repo-00": ["platform-team"],
            }
        )


def create_test_app():
    app = Flask(
        "app", static_folder=os.path.join(APP_DIR, "static"), static_url_path="/assets"
    )
    app.secret_key = "test"
    configure_jinja(app)
    app.register_blueprint(main)
    app.register_blueprint(repository_stats_main, url_prefix="/repository-stats/")
    return app


class RepositoryStatsTestCase(unittest.TestCase):
    repository_class = FakeVisibilityRepository

    def setUp(self):
        self.client = create_test_app().test_client()
        self.repository = self.repository_class()
        for target, kwargs in (
            ("app.shared.middleware.auth.app_config.auth_enabled", {"new": False}),
            (
                "app.projects.repository_stats.routes.main.get_visibility_service",
                {
                    "return_value": VisibilityService(
                        self.repository,
                        FakeOwnership(),
                        "23 October 2026",
                        today=TODAY,
                    )
                },
            ),
        ):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def get(self, url):
        response = self.client.get(url)
        return response, response.get_data(as_text=True)

    def activity_rows(self, body):
        section = body.split('id="activity-table"', 1)[1].split("</tbody>", 1)[0]
        return re.findall(r"<tr class=\"govuk-table__row\">\s*<td", section)

    @staticmethod
    def archived_rows(body):
        """(name, hidden) for every row rendered in the archived table."""
        tbody = body.split('id="archived-table"', 1)[1].split("</tbody>", 1)[0]
        return [
            (name, bool(hidden))
            for hidden, name in re.findall(
                r'<tr class="govuk-table__row" data-org=[^>]*?( hidden)?>\s*<td class="govuk-table__cell">\s*<a [^>]*>([^<]+)<',
                tbody,
            )
        ]

    def visible_archived(self, body):
        return [name for name, hidden in self.archived_rows(body) if not hidden]

    @staticmethod
    def filters(body):
        return body.split('id="visibility-filters"', 1)[1].split("</form>", 1)[0]


def estate_line(total, public, internal, private):
    return (
        f'<p class="govuk-body app-visibility-estate">Current repositories: <strong>{total}</strong> '
        f'<span aria-hidden="true">·</span> Public <strong>{public}</strong> '
        f'<span aria-hidden="true">·</span> Internal <strong>{internal}</strong> '
        f'<span aria-hidden="true">·</span> Private <strong>{private}</strong></p>'
    )


class TestAuth(unittest.TestCase):
    def test_every_route_requires_auth(self):
        client = create_test_app().test_client()
        with patch("app.shared.middleware.auth.app_config.auth_enabled", True):
            for url in (
                "/repository-stats/",
                OVERVIEW_URL,
                CHANGES_URL,
                f"{CHANGES_URL}/changes.csv",
                ARCHIVED_URL,
            ):
                with self.subTest(url=url):
                    response = client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.headers["Location"], "/auth/login")


ROUTES = (
    "/repository-stats/",
    "/repository-stats/overview",
    "/repository-stats/visibility",
    "/repository-stats/visibility/changes.csv",
    "/repository-stats/archived",
)
GITHUB_ROUTES = (
    "/repository-stats/github/login",
    "/repository-stats/github/callback",
    "/repository-stats/github/switch",
)
ACCESS_TEAM = "ministryofjustice/repository-stats-viewers"
ACCESS = "app.projects.repository_stats.services.visibility_access"
MEMBERSHIP = f"{ACCESS}.is_team_member"
SIGN_IN = "app.projects.repository_stats.services.github_sign_in"
GITHUB_LOGIN_URL = "/repository-stats/github/login"
CALLBACK_URL = "/repository-stats/github/callback"
SWITCH_URL = "/repository-stats/github/switch"
NO_ACCESS_HEADING = (
    '<h1 class="govuk-heading-l">You don\'t have access to Repository Stats yet</h1>'
)
UNAVAILABLE_HEADING = "Sorry, we can&#39;t check your access right now"
MICROSOFT_SUB = "waad|pairwise-id"


def login_redirect(location):
    """(path, next) for a redirect to the GitHub login route."""
    parts = urlsplit(location)
    return parts.path, parse_qs(parts.query).get("next")


def microsoft_user(sub=MICROSOFT_SUB):
    return {
        "expires_at": time.time() + 3600,
        "userinfo": {"sub": sub, "nickname": "octo.cat"},
    }


class StatsAccessTestCase(RepositoryStatsTestCase):
    """Auth on, the access team set, signed in with Microsoft but not yet GitHub."""

    def setUp(self):
        super().setUp()
        for target, value in (
            ("app.shared.middleware.auth.app_config.auth_enabled", True),
            (f"{ACCESS}.app_config.github.stats_access_team", ACCESS_TEAM),
            (f"{ACCESS}.get_github_client", lambda: object()),
            (
                f"{SIGN_IN}.app_config.github.stats_oauth",
                SimpleNamespace(client_id="client-id", client_secret="client-secret"),
            ),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with self.client.session_transaction() as flask_session:
            flask_session["user"] = microsoft_user()

    def sign_in_to_github(self, login="octocat", checked_at=None, has_access=True):
        with self.client.session_transaction() as flask_session:
            flask_session[GITHUB_SESSION_KEY] = {
                "login": login,
                "auth_sub": MICROSOFT_SUB,
                "signed_in_at": time.time(),
            }
            if checked_at is not None:
                flask_session[SESSION_KEY] = {
                    ACCESS_TEAM: {
                        "login": login,
                        "has_access": has_access,
                        "checked_at": checked_at,
                    }
                }

    def session(self):
        with self.client.session_transaction() as flask_session:
            return dict(flask_session)

    def start_github_sign_in(self):
        """Go to GitHub; returns the state GitHub would send back."""
        response = self.client.get(GITHUB_LOGIN_URL)
        self.assertEqual(response.status_code, 302)
        return parse_qs(urlsplit(response.location).query)["state"][0]

    def callback(self, query, login="octocat", token=None, user=None):
        token = token or SimpleNamespace(
            status_code=200, ok=True, json=lambda: {"access_token": "gho_x"}
        )
        user = user or SimpleNamespace(
            status_code=200, ok=True, json=lambda: {"login": login}
        )

        def result(value):
            if isinstance(value, Exception):
                raise value
            return value

        with (
            patch(
                f"{SIGN_IN}.requests.post", side_effect=lambda *a, **k: result(token)
            ),
            patch(f"{SIGN_IN}.requests.get", side_effect=lambda *a, **k: result(user)),
        ):
            return self.client.get(f"{CALLBACK_URL}?{urlencode(query)}")


class TestStatsAccess(StatsAccessTestCase):
    def test_every_stats_route_is_access_tested(self):
        rules = {
            rule.rule
            for rule in self.client.application.url_map.iter_rules()
            if rule.endpoint.startswith("repository_stats_main.")
        }
        self.assertEqual(rules, set(ROUTES) | set(GITHUB_ROUTES))

    def test_no_github_sign_in_goes_straight_to_github_and_remembers_the_page(self):
        with patch(MEMBERSHIP) as membership:
            for url in ROUTES:
                with self.subTest(url=url):
                    response = self.client.get(f"{url}?a=1")
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(
                        login_redirect(response.location),
                        (GITHUB_LOGIN_URL, [f"{url}?a=1"]),
                    )
                    response = self.client.get(response.location)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(
                        response.location.startswith(
                            "https://github.com/login/oauth/authorize?"
                        )
                    )
                    self.assertEqual(self.session()["stats_github_next"], f"{url}?a=1")
        membership.assert_not_called()

    def test_github_login_ignores_unsafe_next_and_keeps_remembered_page(self):
        with self.client.session_transaction() as flask_session:
            flask_session["stats_github_next"] = "/repository-stats/archived"
        for next_path in ("https://evil.example/", "//evil.example", "/auth/logout"):
            with self.subTest(next_path=next_path):
                response = self.client.get(
                    f"{GITHUB_LOGIN_URL}?{urlencode({'next': next_path})}"
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    self.session()["stats_github_next"], "/repository-stats/archived"
                )

    def test_confirm_page_is_gone(self):
        self.assertEqual(self.client.get("/repository-stats/github").status_code, 404)

    def test_failed_callback_shows_a_page_rather_than_going_back_to_github(self):
        self.start_github_sign_in()
        for query in ({"error": "access_denied"}, {"state": "wrong", "code": "x"}):
            with self.subTest(query=query):
                response = self.client.get(f"{CALLBACK_URL}?{urlencode(query)}")
                self.assertIn(response.status_code, (200, 400))
                self.assertIsNone(response.location)
                body = response.get_data(as_text=True)
                self.assertIn(f'href="{GITHUB_LOGIN_URL}"', body)

    def test_confirm_page_needs_microsoft_sign_in(self):
        with self.client.session_transaction() as flask_session:
            flask_session.clear()
        for url in (GITHUB_LOGIN_URL, f"{CALLBACK_URL}?code=x&state=y"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, "/auth/login")
        response = self.client.post(SWITCH_URL)
        self.assertEqual(response.location, "/auth/login")

    def sign_in_on_host(self, base_url):
        with self.client.session_transaction(base_url=base_url) as flask_session:
            flask_session["user"] = microsoft_user()

    def test_github_login_redirects_to_github_without_scopes(self):
        self.sign_in_on_host("http://github-community.service.justice.gov.uk")
        response = self.client.get(
            GITHUB_LOGIN_URL, base_url="http://github-community.service.justice.gov.uk"
        )
        self.assertEqual(response.status_code, 302)
        url = urlsplit(response.location)
        self.assertEqual(url.netloc, "github.com")
        self.assertEqual(url.path, "/login/oauth/authorize")
        query = parse_qs(url.query)
        self.assertEqual(query["client_id"], ["client-id"])
        # https even when the request reached the app over http behind the proxy.
        self.assertEqual(
            query["redirect_uri"],
            [
                "https://github-community.service.justice.gov.uk/repository-stats/github/callback"
            ],
        )
        self.assertNotIn("scope", query)
        with self.client.session_transaction(
            base_url="http://github-community.service.justice.gov.uk"
        ) as flask_session:
            self.assertEqual(
                query["state"], [flask_session["stats_github_oauth_state"]]
            )

    def test_redirect_uri_follows_the_request_host(self):
        for host in (
            "github-community-dev.cloud-platform.service.justice.gov.uk",
            "github-community.cloud-platform.service.justice.gov.uk",
        ):
            with self.subTest(host=host):
                self.sign_in_on_host(f"https://{host}")
                response = self.client.get(GITHUB_LOGIN_URL, base_url=f"https://{host}")
                query = parse_qs(urlsplit(response.location).query)
                self.assertEqual(
                    query["redirect_uri"],
                    [f"https://{host}/repository-stats/github/callback"],
                )

    def test_github_login_not_configured(self):
        with patch(
            f"{SIGN_IN}.app_config.github.stats_oauth",
            SimpleNamespace(client_id=None, client_secret=None),
        ):
            response = self.client.get(GITHUB_LOGIN_URL)
        self.assertEqual(response.status_code, 503)
        self.assertIn(
            "GitHub sign-in isn&#39;t available", response.get_data(as_text=True)
        )

    def test_happy_path_member(self):
        page = self.client.get("/repository-stats/overview?open=ministryofjustice")
        to_github = self.client.get(page.location)
        state = parse_qs(urlsplit(to_github.location).query)["state"][0]
        with patch(MEMBERSHIP, return_value=True) as membership:
            response = self.callback({"code": "abc", "state": state})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                response.location, "/repository-stats/overview?open=ministryofjustice"
            )
            # The team was checked in the callback; the page uses that result.
            membership.assert_called_once()
            self.assertEqual(
                membership.call_args.args[:3],
                ("octocat", "ministryofjustice", "repository-stats-viewers"),
            )
            page = self.client.get(response.location)
            self.assertEqual(page.status_code, 200)
            membership.assert_called_once()
        saved = self.session()
        self.assertEqual(saved[GITHUB_SESSION_KEY]["login"], "octocat")
        self.assertEqual(saved[GITHUB_SESSION_KEY]["auth_sub"], MICROSOFT_SUB)
        self.assertIn("signed_in_at", saved[GITHUB_SESSION_KEY])
        self.assertTrue(saved[SESSION_KEY][ACCESS_TEAM]["has_access"])
        self.assertNotIn("stats_github_oauth_state", saved)
        self.assertNotIn("stats_github_next", saved)
        # The GitHub token is never kept.
        self.assertNotIn("gho_x", json.dumps(saved))

    def test_token_exchange_sends_the_code_and_callback_url(self):
        state = self.start_github_sign_in()
        token = SimpleNamespace(
            status_code=200, ok=True, json=lambda: {"access_token": "gho_x"}
        )
        user = SimpleNamespace(
            status_code=200, ok=True, json=lambda: {"login": "octocat"}
        )
        with (
            patch(f"{SIGN_IN}.requests.post", return_value=token) as post,
            patch(f"{SIGN_IN}.requests.get", return_value=user),
            patch(MEMBERSHIP, return_value=True),
        ):
            self.client.get(f"{CALLBACK_URL}?code=abc&state={state}")
        self.assertEqual(post.call_args.kwargs["data"]["code"], "abc")
        self.assertEqual(
            post.call_args.kwargs["data"]["redirect_uri"],
            "https://localhost/repository-stats/github/callback",
        )

    def test_happy_path_without_a_remembered_page_goes_to_stats_home(self):
        state = self.start_github_sign_in()
        with patch(MEMBERSHIP, return_value=True):
            response = self.callback({"code": "abc", "state": state})
        self.assertEqual(response.location, "/repository-stats/")

    def test_unsafe_next_url_is_rejected(self):
        for next_path in (
            "https://evil.example/",
            "//evil.example/repository-stats/",
            "/repository-standards/",
        ):
            with self.subTest(next_path=next_path):
                state = self.start_github_sign_in()
                with self.client.session_transaction() as flask_session:
                    flask_session["stats_github_next"] = next_path
                with patch(MEMBERSHIP, return_value=True):
                    response = self.callback({"code": "abc", "state": state})
                self.assertEqual(response.location, "/repository-stats/")

    def test_not_in_team(self):
        state = self.start_github_sign_in()
        with patch(MEMBERSHIP, return_value=False) as membership:
            self.callback({"code": "abc", "state": state})
            for url in ROUTES:
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 403)
                    self.assertIsNone(response.location)
                    self.assertEqual(response.mimetype, "text/html")
                    body = response.get_data(as_text=True)
                    main_html = body.split("<main", 1)[1].split("</main>", 1)[0]
                    self.assertIn(NO_ACCESS_HEADING, main_html)
                    self.assertIn(
                        "You confirmed your GitHub account as <strong>octocat</strong>.",
                        main_html,
                    )
                    # Slack is the only way to ask; the homepage link comes last.
                    self.assertEqual(
                        re.findall(
                            r'<a [^>]*href="([^"]+)"', main_html.split("</nav>", 1)[1]
                        ),
                        [VISIBILITY_SLACK_CHANNEL_URL, "/"],
                    )
                    self.assertIn(
                        '<p class="govuk-body"><a class="govuk-link" href="/">'
                        "Go to the GitHub Community homepage</a></p>",
                        main_html,
                    )
                    self.assertIn(
                        f'<a class="govuk-link" href="{VISIBILITY_SLACK_CHANNEL_URL}" target="_blank" '
                        f'rel="noopener noreferrer">{VISIBILITY_SLACK_CHANNEL_NAME}',
                        main_html,
                    )
                    self.assertIn(f'action="{SWITCH_URL}"', main_html)
                    self.assertIn("Use a different GitHub account", main_html)
                    self.assertIn("sign out of github.com first", main_html)
                    self.assertNotIn("Repository visibility changes", main_html)
        membership.assert_called_once()

    def test_cancel_on_github(self):
        state = self.start_github_sign_in()
        with patch(MEMBERSHIP) as membership:
            response = self.callback(
                {
                    "error": "access_denied",
                    "error_description": "The user has denied your application access.",
                    "state": state,
                }
            )
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("You didn&#39;t confirm your GitHub account", body)
        self.assertIn(f'href="{GITHUB_LOGIN_URL}"', body)
        self.assertNotIn(GITHUB_SESSION_KEY, self.session())
        membership.assert_not_called()

    def test_bad_missing_or_reused_state(self):
        for name, make_query in (
            ("wrong", lambda state: {"code": "abc", "state": state + "x"}),
            ("missing", lambda state: {"code": "abc"}),
            ("empty", lambda state: {"code": "abc", "state": ""}),
        ):
            with self.subTest(name=name):
                state = self.start_github_sign_in()
                with patch(MEMBERSHIP) as membership:
                    response = self.callback(make_query(state))
                self.assert_state_problem(response)
                membership.assert_not_called()
                # The saved state is used up even when it didn't match.
                self.assertNotIn("stats_github_oauth_state", self.session())

        with self.subTest(name="reused"):
            state = self.start_github_sign_in()
            with patch(MEMBERSHIP, return_value=True):
                self.assertEqual(
                    self.callback({"code": "abc", "state": state}).status_code, 302
                )
            with self.client.session_transaction() as flask_session:
                flask_session.pop(GITHUB_SESSION_KEY)
            self.assert_state_problem(self.callback({"code": "abc", "state": state}))
            self.assertNotIn(GITHUB_SESSION_KEY, self.session())

        with self.subTest(name="never started"):
            with self.client.session_transaction() as flask_session:
                flask_session.pop("stats_github_oauth_state", None)
            self.assert_state_problem(self.callback({"code": "abc", "state": "abc"}))

    def assert_state_problem(self, response):
        self.assertEqual(response.status_code, 400)
        body = response.get_data(as_text=True)
        self.assertIn("Your GitHub sign-in has expired", body)
        self.assertIn(f'href="{GITHUB_LOGIN_URL}"', body)
        self.assertNotIn(GITHUB_SESSION_KEY, self.session())

    def test_other_github_error_or_missing_code(self):
        for query in ({"error": "redirect_uri_mismatch"}, {}):
            with self.subTest(query=query):
                state = self.start_github_sign_in()
                response = self.callback({**query, "state": state})
                self.assertEqual(response.status_code, 400)
                self.assertIn(
                    "We couldn&#39;t confirm your GitHub account",
                    response.get_data(as_text=True),
                )
                self.assertNotIn(GITHUB_SESSION_KEY, self.session())

    def test_token_exchange_failure(self):
        state = self.start_github_sign_in()
        response = self.callback(
            {"code": "abc", "state": state},
            token=SimpleNamespace(
                status_code=200,
                ok=True,
                json=lambda: {"error": "bad_verification_code"},
            ),
        )
        self.assertEqual(response.status_code, 502)
        body = response.get_data(as_text=True)
        self.assertIn("We couldn&#39;t confirm your GitHub account", body)
        self.assertIn(f'href="{GITHUB_LOGIN_URL}"', body)
        self.assertNotIn(GITHUB_SESSION_KEY, self.session())

    def test_user_lookup_failure(self):
        state = self.start_github_sign_in()
        response = self.callback(
            {"code": "abc", "state": state},
            user=SimpleNamespace(status_code=401, ok=False, json=dict),
        )
        self.assertEqual(response.status_code, 502)
        self.assertIn(
            "We couldn&#39;t confirm your GitHub account",
            response.get_data(as_text=True),
        )
        self.assertNotIn(GITHUB_SESSION_KEY, self.session())

    def test_github_down_during_sign_in(self):
        for token, user in (
            (requests.ReadTimeout("slow"), None),
            (SimpleNamespace(status_code=502, ok=False, json=dict), None),
            (None, requests.ConnectionError("down")),
        ):
            with self.subTest(token=token, user=user):
                state = self.start_github_sign_in()
                response = self.callback(
                    {"code": "abc", "state": state}, token=token, user=user
                )
                self.assertEqual(response.status_code, 503)
                body = response.get_data(as_text=True)
                self.assertIn(UNAVAILABLE_HEADING, body)
                self.assertIn("Try again later", body)
                self.assertIn(f'href="{GITHUB_LOGIN_URL}"', body)
                self.assertNotIn(GITHUB_SESSION_KEY, self.session())

    def test_team_check_error_fails_closed(self):
        self.sign_in_to_github()
        for error in (ConnectionError("down"), GitHubAccessCheckError("status 500")):
            with patch(MEMBERSHIP, side_effect=error):
                for url in ROUTES:
                    with self.subTest(error=error, url=url):
                        response = self.client.get(url)
                        self.assertEqual(response.status_code, 503)
                        body = response.get_data(as_text=True)
                        self.assertIn(UNAVAILABLE_HEADING, body)
                        self.assertIn(f'href="{url}"', body)
                        self.assertNotIn("Repository visibility changes", body)
        self.assertNotIn(SESSION_KEY, self.session())

    def test_team_check_error_in_callback_fails_closed(self):
        state = self.start_github_sign_in()
        with patch(MEMBERSHIP, side_effect=ConnectionError("down")):
            response = self.callback({"code": "abc", "state": state})
            self.assertEqual(response.status_code, 302)
            page = self.client.get(response.location)
        self.assertEqual(page.status_code, 503)
        self.assertIn(UNAVAILABLE_HEADING, page.get_data(as_text=True))

    def test_member_with_fresh_cache_is_not_rechecked(self):
        self.sign_in_to_github(checked_at=time.time() - 60)
        with patch(MEMBERSHIP) as membership:
            for url in ROUTES:
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
        membership.assert_not_called()

    def test_hourly_recheck_keeps_a_member_in(self):
        self.sign_in_to_github(checked_at=time.time() - 3601)
        with patch(MEMBERSHIP, return_value=True) as membership:
            self.assertEqual(self.client.get(ROUTES[0]).status_code, 200)
            self.assertEqual(self.client.get(ROUTES[1]).status_code, 200)
        membership.assert_called_once()
        self.assertGreater(
            self.session()[SESSION_KEY][ACCESS_TEAM]["checked_at"], time.time() - 60
        )

    def test_hourly_recheck_denies_someone_removed_from_the_team(self):
        self.sign_in_to_github(checked_at=time.time() - 3601)
        with patch(MEMBERSHIP, return_value=False) as membership:
            response = self.client.get(ROUTES[1])
        self.assertEqual(response.status_code, 403)
        self.assertIn(NO_ACCESS_HEADING, response.get_data(as_text=True))
        # Checked silently with the stored login; no new GitHub sign-in.
        self.assertEqual(membership.call_args.args[0], "octocat")
        self.assertEqual(self.session()[GITHUB_SESSION_KEY]["login"], "octocat")

    def test_new_session_triggers_a_check(self):
        with patch(MEMBERSHIP, return_value=True) as membership:
            for _ in range(2):
                self.client = create_test_app().test_client()
                with self.client.session_transaction() as flask_session:
                    flask_session["user"] = microsoft_user()
                self.sign_in_to_github()
                self.assertEqual(self.client.get(ROUTES[0]).status_code, 200)
        self.assertEqual(membership.call_count, 2)

    def test_github_login_for_another_microsoft_user_is_not_used(self):
        self.sign_in_to_github(checked_at=time.time())
        with self.client.session_transaction() as flask_session:
            flask_session["user"] = microsoft_user("waad|someone-else")
        with patch(MEMBERSHIP) as membership:
            response = self.client.get(ROUTES[0])
        self.assertEqual(
            login_redirect(response.location), (GITHUB_LOGIN_URL, [ROUTES[0]])
        )
        membership.assert_not_called()

    def test_use_a_different_github_account(self):
        self.sign_in_to_github(checked_at=time.time(), has_access=False)
        response = self.client.post(SWITCH_URL)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, GITHUB_LOGIN_URL)
        saved = self.session()
        self.assertNotIn(GITHUB_SESSION_KEY, saved)
        self.assertNotIn(SESSION_KEY, saved)
        self.assertIn("user", saved)
        response = self.client.get(response.location)
        self.assertTrue(
            response.location.startswith("https://github.com/login/oauth/authorize?")
        )
        self.assertEqual(self.client.get(SWITCH_URL).status_code, 405)

    def test_signed_out_user_still_goes_to_login_first(self):
        with self.client.session_transaction() as flask_session:
            flask_session.clear()
        with patch(MEMBERSHIP) as membership:
            for url in ROUTES:
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.location, "/auth/login")
        membership.assert_not_called()

    def test_team_unset_allows_everyone_without_github_sign_in(self):
        with (
            patch(f"{ACCESS}.app_config.github.stats_access_team", None),
            patch(MEMBERSHIP) as membership,
        ):
            for url in ROUTES:
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
        membership.assert_not_called()

    def test_auth_disabled_allows_everyone_without_calling_github(self):
        with self.client.session_transaction() as flask_session:
            flask_session.clear()
        with (
            patch("app.shared.middleware.auth.app_config.auth_enabled", False),
            patch(MEMBERSHIP) as membership,
        ):
            for url in ROUTES:
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
        membership.assert_not_called()

    def test_homepage_card_still_shown(self):
        with patch(MEMBERSHIP, return_value=False):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/repository-stats/"', response.get_data(as_text=True))


class TestSharedAuthRoutes(unittest.TestCase):
    """/auth/logout and /auth/callback (Microsoft sign-in through Auth0)."""

    def setUp(self):
        app = create_test_app()
        with app.app_context():
            from app.shared.routes import auth

        self.auth = auth
        app.register_blueprint(auth.auth_route, url_prefix="/auth")
        self.client = app.test_client()
        with self.client.session_transaction() as flask_session:
            flask_session["user"] = microsoft_user()
            flask_session[GITHUB_SESSION_KEY] = {
                "login": "octocat",
                "auth_sub": MICROSOFT_SUB,
            }
            flask_session[SESSION_KEY] = {ACCESS_TEAM: {"has_access": True}}
            flask_session["stats_github_oauth_state"] = "abc"

    def test_logout_clears_microsoft_and_github_sign_in(self):
        with patch.object(self.auth.auth0_service, "domain", "example.auth0.test"):
            response = self.client.get("/auth/logout")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.location.startswith("https://example.auth0.test/v2/logout")
        )
        with self.client.session_transaction() as flask_session:
            self.assertEqual(dict(flask_session), {})

    def test_new_microsoft_sign_in_gets_a_fresh_team_check(self):
        with patch.object(
            self.auth.auth0_service, "get_access_token", return_value=microsoft_user()
        ):
            self.client.get("/auth/callback")
        with self.client.session_transaction() as flask_session:
            self.assertNotIn(SESSION_KEY, flask_session)
            self.assertEqual(flask_session[GITHUB_SESSION_KEY]["login"], "octocat")


class TestLandingPages(RepositoryStatsTestCase):
    def test_project_home(self):
        response, body = self.get("/repository-stats/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<h1 class="govuk-heading-xl">GitHub Repository Stats</h1>', body)
        self.assertIn(
            '<p class="govuk-body-l">View estate-wide statistics and reports across GitHub Enterprise organisations.</p>',
            body,
        )
        reports = re.findall(
            r'<a class="govuk-link" href="([^"]+)">([^<]+)</a>\s*</h3>\s*<p class="govuk-body-s">([^<]+)</p>',
            body,
        )
        self.assertEqual(
            reports,
            [
                (
                    OVERVIEW_URL,
                    "Repository overview",
                    "View repository totals by organisation, business unit and team.",
                ),
                (
                    CHANGES_URL,
                    "Repository visibility changes",
                    "Track visibility changes, new repositories and deleted repositories over time.",
                ),
                (
                    ARCHIVED_URL,
                    "Archived repositories",
                    "Find archived public repositories and track progress towards making them internal.",
                ),
            ],
        )
        self.assertEqual(
            body.count('<h3 class="govuk-heading-s govuk-!-margin-bottom-1">'), 3
        )
        self.assertEqual(body.count('<p class="govuk-body-s">'), 3)
        self.assertNotIn("govuk-tabs", body)
        self.assertIn("govuk-breadcrumbs", body)

    def test_community_home_has_three_project_cards(self):
        response, body = self.get("/")
        self.assertEqual(response.status_code, 200)
        cards = re.findall(
            r'<h3 class="govuk-heading-s govuk-!-margin-bottom-1">\s*<a href="([^"]+)"[^>]*>([^<]+)</a>',
            body,
        )
        self.assertEqual(
            cards,
            [
                ("/repository-standards/", "GitHub Repository Standards"),
                (
                    "https://github.com/ministryofjustice/github-actions",
                    "Shared GitHub Actions",
                ),
                ("/repository-stats/", "GitHub Repository Stats"),
            ],
        )
        self.assertIn(
            "View estate-wide statistics and reports across GitHub Enterprise organisations.",
            body,
        )
        self.assertIn(
            "View insights and compliance information for GitHub repositories in the Ministry of Justice.",
            body,
        )
        self.assertIn(
            "Reduce duplicate efforts by reusing pre-built GitHub Actions maintained by the Ministry of Justice.",
            body,
        )


class TestVisibilityChangesPage(RepositoryStatsTestCase):
    def test_default_page(self):
        response, body = self.get(CHANGES_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<h1 class="govuk-heading-xl govuk-!-margin-bottom-4">Repository visibility changes</h1>',
            body,
        )
        self.assertIn(
            '<p class="govuk-body-l govuk-!-margin-bottom-4">Track repository visibility changes, new repositories and deleted repositories.</p>',
            body,
        )
        self.assertNotIn(NO_HEADING, body)
        self.assertIn(LAST_UPDATED_LINE, body)
        self.assertNotIn("Summary", body)
        self.assertIn(
            '<input class="govuk-input" id="from" name="from" type="date" value="" min="2026-08-01" max="2026-10-01">',
            body,
        )
        self.assertIn(
            '<input class="govuk-input" id="to" name="to" type="date" value="" min="2026-08-01" max="2026-10-01">',
            body,
        )
        self.assertIn(estate_line(34, 3, 31, 0), body)
        for label in ("Visibility changes", "New repositories", "Deleted repositories"):
            self.assertIn(f'<dt class="app-visibility-stats__label">{label}</dt>', body)
        self.assertIn(
            '<caption class="govuk-table__caption govuk-visually-hidden">Changes by transition</caption>',
            body,
        )
        self.assertIn("All activity (33)", body)
        self.assertIn("Showing 1 to 25 of 33", body)
        self.assertEqual(len(self.activity_rows(body)), 25)
        self.assertIn(
            'href="/assets/projects/repository_stats/stylesheets/visibility.css"', body
        )
        self.assertNotIn("There is a problem", body)
        self.assertIn(
            "<title>Repository visibility changes - GitHub Repository Stats",
            body.replace("\n", "").replace("  ", ""),
        )

    def test_is_a_standalone_page(self):
        _, body = self.get(f"{CHANGES_URL}?tab=archived")
        self.assertNotIn("govuk-tabs", body)
        self.assertNotIn('name="tab"', body)
        self.assertNotIn("tab=", body)
        self.assertNotIn("#archived", body)
        self.assertNotIn("visibility.js", body)
        self.assertNotIn("govuk-notification-banner", body)
        self.assertNotIn("Archived public repositories", body)
        self.assertIn("All activity (33)", body)

    def test_breadcrumbs_link_back_to_project(self):
        _, body = self.get(CHANGES_URL)
        crumbs = body.split('class="govuk-breadcrumbs', 1)[1].split("</nav>", 1)[0]
        self.assertIn('href="/"', crumbs)
        self.assertIn('href="/repository-stats/">GitHub Repository Stats</a>', crumbs)
        self.assertIn("Repository visibility changes", crumbs)

    def test_filter_form(self):
        _, body = self.get(f"{CHANGES_URL}?activity=new&sort=repository&dir=asc&page=2")
        filters = self.filters(body)
        self.assertIn(f'action="{CHANGES_URL}" class="app-visibility-filters"', body)
        for field in (
            'id="org"',
            'id="business_unit"',
            'id="q"',
            'id="from"',
            'id="to"',
        ):
            self.assertIn(field, filters)
        self.assertIn('<input type="hidden" name="activity" value="new">', filters)
        self.assertIn('<input type="hidden" name="sort" value="repository">', filters)
        self.assertNotIn('type="hidden" name="page"', filters)
        row = filters.split('<div class="app-visibility-filter-row">', 1)[1]
        self.assertLess(row.index('id="to"'), row.index("Apply filters"))
        self.assertLess(row.index("Apply filters"), row.index("Clear filters"))
        self.assertIn(
            f'<a class="govuk-link" id="clear-filters" href="{CHANGES_URL}">Clear filters</a>',
            filters,
        )

    def test_organisations_from_the_data(self):
        _, body = self.get(CHANGES_URL)
        self.assertIn(f'<option value="{ORG}">{ORG}</option>', body)
        self.assertIn(f'<option value="{OTHER_ORG}">{OTHER_ORG}</option>', body)
        _, body = self.get(f"{CHANGES_URL}?org={OTHER_ORG}")
        self.assertIn(
            f'<option value="{OTHER_ORG}" selected>{OTHER_ORG}</option>', body
        )
        self.assertIn(estate_line(1, 1, 0, 0), body)
        self.assertIn("All activity (0)", body)

    def test_each_filter_switches_to_summary_heading(self):
        for params, expected in (
            (f"org={ORG}", "Summary, all dates"),
            ("business_unit=HMPPS", "Summary, all dates"),
            ("q=repo", "Summary, all dates"),
            ("from=2026-08-10", "Summary, 10 August to 1 October 2026"),
            ("to=2026-09-18", "Summary, 1 August to 18 September 2026"),
            (
                f"org={ORG}&from=2025-12-10",
                "Summary, 1 August to 1 October 2026",
            ),
            (
                "business_unit=HMPPS&from=2026-08-10&to=2026-09-18",
                "Summary, 10 August to 18 September 2026",
            ),
        ):
            with self.subTest(params=params):
                _, body = self.get(f"{CHANGES_URL}?{params}")
                self.assertIn(f'<h2 class="govuk-heading-m">{expected}</h2>', body)
                self.assertNotIn(NO_HEADING, body)
                self.assertIn(LAST_UPDATED_LINE, body)

    def test_activity_sort_and_page_keep_unfiltered_view(self):
        for params in (
            "activity=new",
            "sort=repository&dir=asc",
            "page=2",
            "org=&business_unit=&q=&from=&to=",
        ):
            with self.subTest(params=params):
                _, body = self.get(f"{CHANGES_URL}?{params}")
                self.assertNotIn(NO_HEADING, body)
                self.assertIn(LAST_UPDATED_LINE, body)
                self.assertNotIn("Summary,", body)

    def test_current_repositories_line(self):
        _, body = self.get(f"{CHANGES_URL}?from=2026-09-01&to=2026-09-05")
        self.assertIn(estate_line(34, 3, 31, 0), body)
        _, body = self.get(f"{CHANGES_URL}?business_unit=HMPPS")
        self.assertIn(estate_line(1, 0, 1, 0), body)

    def test_activity_table_unchanged(self):
        _, body = self.get(CHANGES_URL)
        head = body.split('id="activity-table"', 1)[1].split("</thead>", 1)[0]
        self.assertEqual(
            len(re.findall(r'<a class="govuk-link app-visibility-sort"', head)), 6
        )
        for label in (
            "Repository",
            "Organisation",
            "Business unit",
            "Activity",
            "Date",
            "By",
        ):
            self.assertIn(label, head)
        self.assertIn('aria-sort="descending"', head)
        self.assertEqual(body.count('id="activity"'), 1)
        self.assertEqual(body.count('id="activity-table"'), 1)
        self.assertIn(f'action="{CHANGES_URL}#activity-table"', body)

    def test_sorting(self):
        _, body = self.get(f"{CHANGES_URL}?sort=repository&dir=asc")
        self.assertIn('aria-sort="ascending"', body)
        table = body.split('id="activity-table"', 1)[1]
        rows = re.findall(r"github.com/ministryofjustice/([\w-]+)\"", table)
        self.assertEqual(rows[:2], ["sample-archived-moved", "sample-new"])
        self.assertIn("=cmd|evil", table.split("</tbody>")[0])

    def test_pagination(self):
        _, body = self.get(f"{CHANGES_URL}?page=2")
        self.assertIn("Showing 26 to 33 of 33", body)
        self.assertEqual(len(self.activity_rows(body)), 8)
        _, body = self.get(f"{CHANGES_URL}?page=99")
        self.assertIn("Showing 26 to 33 of 33", body)
        self.assertIn('aria-current="page"', body)

    def test_links_keep_filters_without_default_dates(self):
        _, body = self.get(f"{CHANGES_URL}?business_unit=HMPPS&q=sample")
        links = re.findall(rf'href="({CHANGES_URL}\?[^"]*)"', body)
        self.assertTrue(any("sort=" in link for link in links))
        for link in links:
            self.assertIn("business_unit=HMPPS", link)
            self.assertNotIn("2026-", link)
        _, body = self.get(f"{CHANGES_URL}?q=repo")
        pages = re.findall(rf'href="({CHANGES_URL}\?[^"]*page=\d[^"]*)"', body)
        self.assertTrue(pages)
        for link in pages:
            self.assertIn("q=repo", link)
            self.assertTrue(link.endswith("#activity-table"))

    def test_custom_range_links_carry_dates(self):
        _, body = self.get(f"{CHANGES_URL}?from=2026-08-02&to=2026-09-20")
        self.assertIn(
            '<h2 class="govuk-heading-m">Summary, 2 August to 20 September 2026</h2>',
            body,
        )
        self.assertIn("from=2026-08-02&amp;to=2026-09-20&amp;sort=repository", body)

    def test_filters(self):
        _, body = self.get(f"{CHANGES_URL}?q=repo-0")
        self.assertIn("All activity (10)", body)
        _, body = self.get(f"{CHANGES_URL}?business_unit=HMPPS")
        self.assertIn("All activity (1)", body)
        self.assertIn('<option value="HMPPS" selected>HMPPS</option>', body)
        _, body = self.get(f"{CHANGES_URL}?org=someone-else")
        self.assertIn("Nothing to show from 1 August 2026 to 25 September 2026.", body)

    def test_activity_type(self):
        _, body = self.get(f"{CHANGES_URL}?activity=new")
        self.assertIn("New repositories (1)", body)
        self.assertNotIn(NO_HEADING, body)
        self.assertIn(LAST_UPDATED_LINE, body)
        _, body = self.get(f"{CHANGES_URL}?activity=public-to-internal")
        self.assertIn("Public to internal (31)", body)
        form = body.split(f'action="{CHANGES_URL}#activity-table"', 1)[1].split(
            "</form>", 1
        )[0]
        self.assertNotIn('name="activity" value=', form.split("<select", 1)[0])

    def assert_date_error(self, url, field, message):
        response, body = self.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("There is a problem", body)
        escaped = message.replace("'", "&#39;")
        self.assertIn(f'<a href="#{field}">{escaped}</a>', body)
        self.assertIn(f'id="{field}-error"', self.filters(body))
        self.assertIn(escaped, self.filters(body))
        self.assertIn('<h2 class="govuk-heading-m">Summary</h2>', body)
        self.assertIn("Enter a valid date range to see visibility changes.", body)

    def test_from_only_runs_to_today(self):
        _, body = self.get(f"{CHANGES_URL}?from=2026-09-11")
        self.assertNotIn("There is a problem", body)
        self.assertIn(
            '<h2 class="govuk-heading-m">Summary, 11 September to 1 October 2026</h2>',
            body,
        )
        self.assertIn("All activity (2)", body)
        response = self.client.get(f"{CHANGES_URL}/changes.csv?from=2026-09-11")
        self.assertIn(
            "filename=repository-activity-2026-09-11-to-2026-10-01.csv",
            response.headers["Content-Disposition"],
        )

    def test_to_only_starts_at_the_earliest_snapshot(self):
        _, body = self.get(f"{CHANGES_URL}?to=2026-08-05")
        self.assertNotIn("There is a problem", body)
        self.assertIn(
            '<h2 class="govuk-heading-m">Summary, 1 August to 5 August 2026</h2>', body
        )
        self.assertIn("All activity (4)", body)

    def test_from_before_the_earliest_snapshot_is_clamped_not_an_error(self):
        _, body = self.get(f"{CHANGES_URL}?from=2026-07-01&to=2026-08-05")
        self.assertNotIn("There is a problem", body)
        self.assertNotIn("govuk-error-message", body)
        self.assertIn(
            '<h2 class="govuk-heading-m">Summary, 1 August to 5 August 2026</h2>', body
        )
        self.assertIn("All activity (4)", body)
        self.assertIn('id="from" name="from" type="date" value="2026-07-01"', body)
        self.assertIn('id="to" name="to" type="date" value="2026-08-05"', body)

    def test_from_only_before_the_earliest_snapshot_is_clamped(self):
        _, body = self.get(f"{CHANGES_URL}?from=2025-12-10")
        self.assertNotIn("There is a problem", body)
        self.assertIn(
            '<h2 class="govuk-heading-m">Summary, 1 August to 1 October 2026</h2>', body
        )

    def test_to_before_the_earliest_snapshot_is_empty_not_an_error(self):
        _, body = self.get(f"{CHANGES_URL}?to=2026-07-01")
        self.assertNotIn("There is a problem", body)
        self.assertIn("Nothing to show from 1 July 2026 to 1 July 2026.", body)

    def test_today_is_allowed(self):
        _, body = self.get(f"{CHANGES_URL}?from=2026-10-01&to=2026-10-01")
        self.assertNotIn("There is a problem", body)

    def test_single_day_heading(self):
        for params, expected in (
            ("from=2026-10-01", "Summary, 1 October 2026"),
            ("to=2026-08-01", "Summary, 1 August 2026"),
            ("from=2026-09-10&to=2026-09-10", "Summary, 10 September 2026"),
            ("from=2026-07-01&to=2026-08-01", "Summary, 1 August 2026"),
        ):
            with self.subTest(params=params):
                _, body = self.get(f"{CHANGES_URL}?{params}")
                self.assertNotIn("There is a problem", body)
                self.assertIn(f'<h2 class="govuk-heading-m">{expected}</h2>', body)

    def test_single_day_csv_filename_unchanged(self):
        response = self.client.get(
            f"{CHANGES_URL}/changes.csv?from=2026-09-10&to=2026-09-10"
        )
        self.assertIn(
            "2026-09-10-to-2026-09-10", response.headers["Content-Disposition"]
        )

    def test_from_after_the_latest_snapshot_shows_empty_state(self):
        response, body = self.get(f"{CHANGES_URL}?from=2026-09-28")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("There is a problem", body)
        self.assertNotIn("govuk-error-message", body)
        self.assertIn(
            '<h2 class="govuk-heading-m">Summary, 28 September to 1 October 2026</h2>',
            body,
        )
        self.assertIn("Nothing to show from 28 September 2026 to 1 October 2026.", body)

    def test_future_from(self):
        for url in (
            f"{CHANGES_URL}?from=2026-10-02",
            f"{CHANGES_URL}?from=2026-10-02&to=2026-10-01",
        ):
            with self.subTest(url=url):
                self.assert_date_error(
                    url, "from", "The 'from' date must be today or in the past"
                )

    def test_future_to(self):
        self.assert_date_error(
            f"{CHANGES_URL}?to=2026-10-02",
            "to",
            "The 'to' date must be today or in the past",
        )

    def test_from_after_to(self):
        self.assert_date_error(
            f"{CHANGES_URL}?from=2026-09-02&to=2026-09-01",
            "from",
            "The 'from' date must be the same as or before the 'to' date",
        )

    def test_date_inputs_stop_at_earliest_snapshot_and_today(self):
        _, body = self.get(f"{CHANGES_URL}?from=2026-08-02")
        self.assertIn(
            'id="from" name="from" type="date" value="2026-08-02" min="2026-08-01" max="2026-10-01">',
            body,
        )
        self.assertIn(
            'id="to" name="to" type="date" value="" min="2026-08-01" max="2026-10-01">',
            body,
        )

    def test_invalid_range_shows_error(self):
        response, body = self.get(f"{CHANGES_URL}?from=2026-09-30&to=2026-08-01")
        self.assertEqual(response.status_code, 200)
        self.assertIn("There is a problem", body)
        self.assertIn(
            "The &#39;from&#39; date must be the same as or before the &#39;to&#39; date",
            body,
        )
        self.assertIn('<h2 class="govuk-heading-m">Summary</h2>', body)
        self.assertIn('id="from-error"', self.filters(body))
        self.assertIn("Enter a valid date range to see visibility changes.", body)
        self.assertIn(
            "Error: Repository visibility changes",
            body.replace("\n", "").replace("  ", ""),
        )

    def test_csv_link_carries_current_params(self):
        _, body = self.get(
            f"{CHANGES_URL}?org={ORG}&business_unit=HMPPS&q=repo"
            "&from=2026-08-02&to=2026-09-20&activity=changes&sort=repository&dir=asc"
        )
        link = re.search(
            r'<a class="govuk-button govuk-button--secondary[^"]*" role="button" draggable="false"[^>]*href="([^"]+)">Download CSV</a>',
            body,
        )
        self.assertEqual(
            link.group(1).replace("&amp;", "&"),
            f"{CHANGES_URL}/changes.csv?org={ORG}&business_unit=HMPPS&q=repo"
            "&from=2026-08-02&to=2026-09-20&activity=changes&sort=repository&dir=asc",
        )
        _, body = self.get(CHANGES_URL)
        self.assertIn(
            f"{CHANGES_URL}/changes.csv?org=&amp;business_unit=&amp;q=&amp;from=&amp;to=&amp;activity=all&amp;sort=date&amp;dir=desc",
            body,
        )


class TestOrganisationDisplayNames(RepositoryStatsTestCase):
    NAMES = MappingProxyType(
        {ORG: "Example Justice Organisation", OTHER_ORG: "Analytical Example"}
    )

    def setUp(self):
        super().setUp()
        self.repository.display_names = self.NAMES

    def org_cells(self, body):
        return re.findall(
            r'<td class="govuk-table__cell app-visibility-org-cell">([^<]*)</td>', body
        )

    def test_tables_show_display_names_falling_back_to_the_login(self):
        self.repository.display_names = {ORG: "Example Justice Organisation"}
        for url in (f"{CHANGES_URL}?activity=all", f"{ARCHIVED_URL}?only_public=0"):
            with self.subTest(url=url):
                _, body = self.get(url)
                cells = set(self.org_cells(body))
                self.assertIn("Example Justice Organisation", cells)
                self.assertNotIn(ORG, cells)
                self.assertLessEqual(cells, {"Example Justice Organisation", OTHER_ORG})

    def test_filter_options_show_display_names_with_login_values(self):
        for url in (CHANGES_URL, ARCHIVED_URL):
            with self.subTest(url=url):
                _, body = self.get(f"{url}?org={OTHER_ORG}")
                filters = self.filters(body)
                self.assertIn(
                    f'<option value="{ORG}">Example Justice Organisation</option>',
                    filters,
                )
                self.assertIn(
                    f'<option value="{OTHER_ORG}" selected>Analytical Example</option>',
                    filters,
                )

    def test_archived_rows_keep_the_login_for_filtering(self):
        _, body = self.get(ARCHIVED_URL)
        self.assertIn(f'data-org="{ORG}"', body)
        self.assertNotIn('data-org="Example Justice Organisation"', body)

    def test_csv_keeps_the_login(self):
        response = self.client.get(f"{CHANGES_URL}/changes.csv?from=2026-08-01")
        text = response.get_data(as_text=True)
        logins = {row[1] for row in list(csv.reader(io.StringIO(text)))[1:]}
        self.assertEqual(logins, {ORG})
        self.assertNotIn("Example Justice Organisation", text)
        self.assertNotIn("Analytical Example", text)

    def test_csv_sort_by_organisation_matches_the_table(self):
        # "Analytical Example" sorts before "Example Justice Organisation",
        # the reverse of the two organisations' login order.
        self.repository.events.append(
            VisibilityEvent(
                300,
                OTHER_ORG,
                "mas-model",
                "changed",
                AUG_1,
                "scan",
                "public",
                "internal",
            )
        )
        params = "activity=all&from=2026-08-01&to=2026-09-25&sort=organisation&dir=asc"
        _, body = self.get(f"{CHANGES_URL}?{params}")
        table = body.split('id="activity-table"', 1)[1]
        table_order = re.findall(r"github.com/([\w.-]+)/[\w.-]+\"", table)

        response = self.client.get(f"{CHANGES_URL}/changes.csv?{params}")
        rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))[1:]
        csv_order = [row[1] for row in rows]

        self.assertEqual(csv_order[: len(table_order)], table_order)
        self.assertEqual(csv_order[0], OTHER_ORG)


class TestWideTablesScroll(RepositoryStatsTestCase):
    def test_each_table_is_in_a_focusable_scroll_region(self):
        for url, label, table, scroll_classes in (
            (
                CHANGES_URL + "?activity=all",
                "Visibility changes table",
                '<table class="govuk-table">',
                "app-table-scroll",
            ),
            (
                OVERVIEW_URL,
                "Repository overview table",
                '<table class="govuk-table app-overview-table"',
                "app-table-scroll app-table-scroll--overview",
            ),
            (
                ARCHIVED_URL,
                "Archived repositories table",
                '<table class="govuk-table app-visibility-archived-table"',
                "app-table-scroll",
            ),
        ):
            with self.subTest(url=url):
                _, body = self.get(url)
                region = (
                    f'<div class="{scroll_classes}" role="region" '
                    f'aria-label="{label}" tabindex="0"'
                )
                self.assertIn(region, body)
                self.assertLess(body.index(region), body.index(table))


class TestLastUpdatedLine(RepositoryStatsTestCase):
    def test_changes_page_shows_line_below_intro(self):
        _, body = self.get(CHANGES_URL)
        self.assertEqual(body.count(LAST_UPDATED_LINE), 1)
        intro = body.index('<p class="govuk-body-l')
        self.assertLess(intro, body.index(LAST_UPDATED_LINE))
        self.assertLess(body.index(LAST_UPDATED_LINE), body.index("<form"))

    def test_archived_page_shows_line_below_heading(self):
        _, body = self.get(ARCHIVED_URL)
        self.assertEqual(body.count(LAST_UPDATED_LINE), 1)
        self.assertLess(
            body.index('<h1 class="govuk-heading-xl'), body.index(LAST_UPDATED_LINE)
        )
        self.assertLess(body.index(LAST_UPDATED_LINE), body.index("<form"))

    def test_line_still_shown_when_filtered(self):
        _, body = self.get(f"{CHANGES_URL}?org=ministryofjustice")
        self.assertIn(LAST_UPDATED_LINE, body)

    def test_no_successful_run_omits_line_but_keeps_data(self):
        self.repository.last_run_finished_at = None
        for url in (CHANGES_URL, ARCHIVED_URL):
            with self.subTest(url=url):
                _, body = self.get(url)
                self.assertNotIn('<p class="govuk-body-s">Last updated', body)


HISTORY_START_LINE = '<p class="govuk-body-s">Showing changes since: 17 August 2026</p>'


class TestHistoryStartLine(RepositoryStatsTestCase):
    def test_shown_directly_above_last_updated_on_the_changes_page(self):
        _, body = self.get(CHANGES_URL)
        self.assertEqual(body.count(HISTORY_START_LINE), 1)
        self.assertRegex(
            body, re.escape(HISTORY_START_LINE) + r"\s*" + re.escape(LAST_UPDATED_LINE)
        )
        self.assertLess(body.index(HISTORY_START_LINE), body.index("<form"))

    def test_uses_the_config_constant(self):
        self.assertEqual(VISIBILITY_HISTORY_START_DATE, "17 August 2026")

    def test_shown_without_a_last_updated_line(self):
        self.repository.last_run_finished_at = None
        _, body = self.get(CHANGES_URL)
        self.assertIn(HISTORY_START_LINE, body)

    def test_not_on_the_archived_page(self):
        _, body = self.get(ARCHIVED_URL)
        self.assertNotIn("Showing changes since", body)


class TestNoImportedDatesNote(RepositoryStatsTestCase):
    def test_not_shown_even_with_imported_data(self):
        self.repository.imported_events = True
        for url in (CHANGES_URL, ARCHIVED_URL):
            with self.subTest(url=url):
                _, body = self.get(url)
                self.assertNotIn("imported-dates-note", body)
                self.assertNotIn("Dates between", body)


class TestNoSnapshots(RepositoryStatsTestCase):
    repository_class = EmptyVisibilityRepository

    def test_changes_empty_state(self):
        response, body = self.get(CHANGES_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn("No visibility snapshots have been captured yet.", body)
        self.assertNotIn("Last updated", body)

    def test_archived_empty_state(self):
        response, body = self.get(ARCHIVED_URL)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Last updated", body)
        self.assertIn("No archived public repositories match your filters.", body)


class TestActivityCsv(RepositoryStatsTestCase):
    def test_csv_download(self):
        response = self.client.get(
            f"{CHANGES_URL}/changes.csv?from=2026-08-01&to=2026-09-25"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.mimetype.startswith("text/csv"))
        self.assertEqual(
            response.headers["Content-Disposition"],
            "attachment; filename=repository-activity-2026-08-01-to-2026-09-25.csv",
        )
        rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
        self.assertEqual(
            rows[0],
            ["repository", "organisation", "business_unit", "activity", "date", "by"],
        )
        self.assertEqual(len(rows), 34)
        deleted = [row for row in rows if row[3].startswith("Deleted")]
        self.assertEqual(deleted[0][0], "'=cmd|evil")

    def test_csv_respects_filters(self):
        response = self.client.get(f"{CHANGES_URL}/changes.csv?activity=new")
        rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
        self.assertEqual([row[0] for row in rows[1:]], ["sample-new"])

    def test_csv_blank_dates_use_default_range(self):
        response = self.client.get(
            f"{CHANGES_URL}/changes.csv?org=&business_unit=&q=&from=&to=&activity=all&sort=date&dir=desc"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "filename=repository-activity-2026-08-01-to-2026-09-25.csv",
            response.headers["Content-Disposition"],
        )
        self.assertEqual(len(response.get_data(as_text=True).strip().splitlines()), 34)

    def test_csv_invalid_dates(self):
        response = self.client.get(
            f"{CHANGES_URL}/changes.csv?from=2026-09-30&to=2026-08-01"
        )
        self.assertEqual(response.status_code, 400)


PROGRESS_NOTE = "Progress is for all organisations and is not affected by filters"


class TestArchivedRepositoriesPage(RepositoryStatsTestCase):
    def test_default_page(self):
        response, body = self.get(ARCHIVED_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<h1 class="govuk-heading-xl govuk-!-margin-bottom-4">Archived public repositories</h1>',
            body,
        )
        self.assertNotIn(NO_HEADING, body)
        self.assertIn(LAST_UPDATED_LINE, body)
        self.assertIn(
            "Archived repositories must be changed from public to internal on or before 23 October 2026.",
            body,
        )
        self.assertIn(
            'C0AJBK3P5A8" target="_blank" rel="noopener noreferrer">#ask-developer-experience<span class="govuk-visually-hidden"> (opens in new tab)</span></a>',
            body,
        )
        self.assertNotIn(" Slack channel", body)
        self.assertIn('<details class="govuk-details">', body)
        self.assertNotIn('<details class="govuk-details" open', body)
        self.assertIn("How to change a repository&#39;s visibility", body)
        self.assertIn("<strong>Unarchive this repository</strong>", body)
        self.assertIn(
            "1 of 2 archived public repositories have been made internal</p>", body
        )
        self.assertIn(
            '<p class="govuk-body govuk-!-margin-bottom-1 app-visibility-secondary-text">50% complete</p>',
            body,
        )
        self.assertIn("width: 50%", body)
        self.assertIn("asset-alpha", body)
        self.assertIn("Office of the CTO", body)
        self.assertEqual(self.visible_archived(body), ["asset-alpha"])
        self.assertIn(("sample-archived-moved", True), self.archived_rows(body))
        self.assertIn(
            'href="/assets/projects/repository_stats/stylesheets/visibility.css"', body
        )

    def test_section_order(self):
        for params in ("", "q=asset", "only_public=0"):
            with self.subTest(params=params):
                _, body = self.get(f"{ARCHIVED_URL}?{params}")
                order = [
                    body.index(text)
                    for text in (
                        LAST_UPDATED_LINE,
                        "govuk-notification-banner",
                        '<h2 class="govuk-heading-m">Progress</h2>',
                        PROGRESS_NOTE,
                        '<h2 class="govuk-heading-m">Find repositories</h2>',
                        "Only show repositories that are still public",
                        "Apply filters",
                        '<details class="govuk-details">',
                        "first seen archived",
                    )
                ]
                self.assertEqual(order, sorted(order))
                self.assertEqual(body.count(PROGRESS_NOTE), 1)

    def test_is_a_standalone_page_without_dates(self):
        _, body = self.get(
            f"{ARCHIVED_URL}?tab=changes&from=2026-09-30&to=2026-08-01&activity=new&sort=repository&page=2"
        )
        self.assertNotIn("govuk-tabs", body)
        self.assertNotIn('name="from"', body)
        self.assertNotIn('name="to"', body)
        self.assertNotIn('name="tab"', body)
        self.assertNotIn('name="activity"', body)
        self.assertNotIn('name="sort"', body)
        self.assertNotIn(
            "2026-",
            body.split("<main", 1)[1]
            .split("</main>", 1)[0]
            .split("govuk-table__body", 1)[0],
        )
        self.assertNotIn("There is a problem", body)
        self.assertNotIn("govuk-error-message", body)
        self.assertNotIn("Error:", body)
        self.assertNotIn('id="activity-table"', body)
        self.assertNotIn("changes.csv", body)
        self.assertNotIn("visibility.js", body)
        self.assertNotIn(NO_HEADING, body)
        self.assertIn(LAST_UPDATED_LINE, body)

    def test_breadcrumbs_link_back_to_project(self):
        _, body = self.get(ARCHIVED_URL)
        crumbs = body.split('class="govuk-breadcrumbs', 1)[1].split("</nav>", 1)[0]
        self.assertIn('href="/repository-stats/">GitHub Repository Stats</a>', crumbs)
        self.assertIn("Archived repositories", crumbs)

    def test_no_summary_heading_with_or_without_filters(self):
        # Progress no longer follows the filters, so there's no filtered "Summary".
        for params in (
            "",
            "org=&business_unit=&q=",
            "from=2026-08-02&to=2026-09-01",
            "only_public=0",
            "business_unit=Office+of+the+CTO",
            f"org={ORG}",
            "q=asset",
        ):
            with self.subTest(params=params):
                _, body = self.get(f"{ARCHIVED_URL}?{params}")
                self.assertNotIn(NO_HEADING, body)
                self.assertNotIn("Summary", body)
                self.assertIn(LAST_UPDATED_LINE, body)

    def test_filter_form(self):
        _, body = self.get(f"{ARCHIVED_URL}?business_unit=HMPPS&only_public=0")
        filters = self.filters(body)
        self.assertIn(
            f'action="{ARCHIVED_URL}#visibility-filters" class="app-visibility-filters app-visibility-filters--compact"',
            body,
        )
        for field in ('id="org"', 'id="business_unit"', 'id="q"'):
            self.assertIn(field, filters)
        self.assertIn('<input type="hidden" name="only_public" value="0">', filters)
        self.assertEqual(filters.count('name="only_public"'), 2)  # fallback + box
        self.assertIn('name="only_public" type="checkbox" value="1">', filters)
        self.assertNotIn('type="hidden" name="business_unit"', filters)
        self.assertEqual(filters.count("<button"), 1)
        self.assertIn("Apply filters", filters)
        self.assertNotIn("Update list", body)
        self.assertEqual(body.count(f'action="{ARCHIVED_URL}#visibility-filters"'), 1)
        self.assertIn(
            f'<a class="govuk-link" id="clear-filters" href="{ARCHIVED_URL}#visibility-filters">Clear filters</a>',
            filters,
        )

    def test_filters_narrow_the_list_but_not_progress(self):
        all_orgs = "1 of 2 archived public repositories have been made internal</p>"
        no_match = '<div id="archived-no-match">'
        for params, shown in (
            ("business_unit=HMPPS", []),
            ("q=asset", ["asset-alpha"]),
            (f"org={OTHER_ORG}", []),
            ("only_public=0", ["asset-alpha", "sample-archived-moved"]),
        ):
            with self.subTest(params=params):
                _, body = self.get(f"{ARCHIVED_URL}?{params}")
                self.assertIn(all_orgs, body)
                self.assertIn("width: 50%", body)
                self.assertEqual(self.visible_archived(body), shown)
                self.assertIn(
                    "No archived public repositories match your filters. Try clearing your filters.",
                    body,
                )
                if shown:
                    self.assertIn('<div id="archived-no-match" hidden>', body)
                    self.assertNotIn('id="archived-table" hidden', body)
                    self.assertNotIn('id="archived-table-region" hidden', body)
                else:
                    self.assertIn(no_match, body)
                    self.assertIn('id="archived-table" hidden', body)
                    self.assertIn('id="archived-table-region" hidden', body)

    def test_checkbox_is_inside_the_filter_form(self):
        _, body = self.get(f"{ARCHIVED_URL}?business_unit=HMPPS&q=repo&org={ORG}")
        filters = self.filters(body)
        self.assertIn('name="only_public" type="checkbox" value="1" checked', filters)
        self.assertIn('value="HMPPS" selected', filters)
        self.assertIn('value="repo" autocomplete="off"', filters)
        _, body = self.get(f"{ARCHIVED_URL}?only_public=0&only_public=0")
        self.assertIn(
            'name="only_public" type="checkbox" value="1">', self.filters(body)
        )

    def test_compact_layout_classes(self):
        _, body = self.get(ARCHIVED_URL)
        self.assertIn(
            'class="govuk-notification-banner app-visibility-banner--full-width"', body
        )
        self.assertIn(
            '<div class="govuk-!-margin-bottom-4" id="archived-progress">', body
        )
        self.assertIn(
            '<div class="app-visibility-progress govuk-!-margin-bottom-2" aria-hidden="true">',
            body,
        )
        self.assertIn(
            'class="app-visibility-filters app-visibility-filters--compact"', body
        )
        self.assertIn(
            'class="govuk-form-group govuk-!-margin-bottom-4"', self.filters(body)
        )
        _, changes = self.get(CHANGES_URL)
        self.assertNotIn("app-visibility-filters--compact", changes)

    def test_filters_return_to_the_filter_panel(self):
        _, body = self.get(f"{ARCHIVED_URL}?q=asset")
        self.assertEqual(body.count('id="visibility-filters"'), 1)
        self.assertIn(f'action="{ARCHIVED_URL}#visibility-filters"', body)
        self.assertIn(f'href="{ARCHIVED_URL}#visibility-filters">Clear filters', body)
        self.assertNotIn(f'action="{ARCHIVED_URL}"', body)

    def test_old_query_strings_still_work(self):
        _, body = self.get(f"{ARCHIVED_URL}?only_public=0&only_public=1&q=asset")
        self.assertIn('value="1" checked', self.filters(body))
        self.assertEqual(self.visible_archived(body), ["asset-alpha"])

    def test_no_archived_repositories_at_all(self):
        self.repository.snapshots = {
            d: [s for s in rows if not s.archived]
            for d, rows in self.repository.snapshots.items()
        }
        self.repository.find_first_archived_dates = dict
        _, body = self.get(ARCHIVED_URL)
        self.assertIn("There are no archived public repositories.", body)
        self.assertIn(PROGRESS_NOTE, body)

    def test_show_all_archived(self):
        _, body = self.get(f"{ARCHIVED_URL}?only_public=0")
        table = body.split("govuk-table__body", 1)[1]
        self.assertIn("sample-archived-moved", table)
        self.assertIn("Fork", table)
        self.assertLess(
            table.index("asset-alpha"), table.index("sample-archived-moved")
        )

    def test_table_unchanged(self):
        _, body = self.get(f"{ARCHIVED_URL}?only_public=0")
        head = body.split('<thead class="govuk-table__head">', 1)[1].split(
            "</thead>", 1
        )[0]
        headers = re.findall(
            r'<th scope="col" class="govuk-table__header">(.*?)</th>', head
        )
        self.assertEqual(
            [re.sub(r"<[^>]+>.*", "", h).strip() for h in headers],
            [
                "Repository",
                "Organisation",
                "Business unit",
                "Archived",
                "Last pushed",
                "Visibility",
            ],
        )
        self.assertIn(
            'Archived <span class="govuk-hint govuk-!-font-size-16 govuk-!-margin-bottom-0">first seen archived</span>',
            head,
        )
        self.assertIn('Repositories (<span id="archived-count">2</span>)', body)

    def test_rows_carry_filter_data(self):
        _, body = self.get(ARCHIVED_URL)
        self.assertEqual(
            self.archived_rows(body),
            [("asset-alpha", False), ("sample-archived-moved", True)],
        )
        self.assertIn(
            f'<tr class="govuk-table__row" data-org="{ORG}" data-business-units=\'["Office of the CTO"]\' data-name="asset-alpha" data-visibility="public">',
            body,
        )
        self.assertIn(
            'data-name="sample-archived-moved" data-visibility="internal" hidden>', body
        )
        self.assertIn('Repositories (<span id="archived-count">1</span>)', body)
        self.assertIn(
            '<p class="govuk-visually-hidden" id="archived-filter-status" role="status" aria-live="polite"></p>',
            body,
        )

    def test_filtered_query_hides_rows_server_side(self):
        _, body = self.get(f"{ARCHIVED_URL}?only_public=0&q=moved")
        self.assertEqual(
            self.archived_rows(body),
            [("asset-alpha", True), ("sample-archived-moved", False)],
        )
        self.assertIn('Repositories (<span id="archived-count">1</span>)', body)
        self.assertIn('<div id="archived-no-match" hidden>', body)
        self.assertIn('<div id="archived-all-internal" hidden>', body)

    def test_all_matching_now_internal(self):
        _, body = self.get(f"{ARCHIVED_URL}?q=moved")
        self.assertEqual(self.visible_archived(body), [])
        self.assertIn('<div id="archived-all-internal">', body)
        self.assertIn('<div id="archived-no-match" hidden>', body)
        self.assertIn('id="archived-table" hidden', body)
        self.assertIn('Repositories (<span id="archived-count">0</span>)', body)

    def test_business_units_are_escaped_in_data_attributes(self):
        with patch.object(
            FakeOwnership,
            "business_units_by_repository",
            lambda _self: {"asset-alpha": ["O'Brien <team>"]},
        ):
            _, body = self.get(ARCHIVED_URL)
        self.assertIn(
            "data-business-units='[\"O\\u0027Brien \\u003cteam\\u003e\"]'", body
        )

    def test_business_units_derived_from_team_access(self):
        with patch.object(
            FakeOwnership,
            "business_units_by_repository",
            lambda _self: RepositoryBusinessUnits(admin_by_github_id={200: ("HMPPS",)}),
        ):
            _, body = self.get(f"{ARCHIVED_URL}?business_unit=HMPPS")
            _, changes = self.get(f"{CHANGES_URL}?business_unit=HMPPS")
        self.assertEqual(self.visible_archived(body), ["asset-alpha"])
        self.assertIn("data-business-units='[\"HMPPS\"]'", body)
        # The changes page uses the same source.
        self.assertIn(estate_line(1, 1, 0, 0), changes)

    def test_live_filter_script_only_on_archived_page(self):
        script = '<script src="/assets/projects/repository_stats/javascript/archived-filters.js"></script>'
        _, archived = self.get(ARCHIVED_URL)
        self.assertEqual(archived.count(script), 1)
        _, changes = self.get(CHANGES_URL)
        self.assertNotIn("archived-filters.js", changes)
        _, index = self.get("/repository-stats/")
        self.assertNotIn("archived-filters.js", index)


class TestRepositoryOverviewPage(RepositoryStatsTestCase):
    def rows(self, body):
        """(kind, name, [total, public, internal, private]) for every table body row."""
        # Team rows for each open business unit live in their own nested table (its
        # own scroll box), inside a <td> of the outer table, so the outer tbody's
        # closing tag isn't the first "</tbody>" in the markup - split on its
        # distinctive (lesser) indentation to avoid stopping at a nested table's.
        tbody = body.split('id="repository-overview"', 1)[1].split(
            "\n        </tbody>\n      </table>", 1
        )[0]
        result = []
        for kind, row in re.findall(
            r'<tr class="govuk-table__row app-overview-row--([a-z-]+)[ "][^>]*>(.*?)</tr>',
            tbody,
            re.DOTALL,
        ):
            name = re.sub(
                r'<span class="govuk-visually-hidden">.*?</span>'
                r"|<[^>]+>",
                "",
                row.split("</th>", 1)[0],
            )
            numbers = re.findall(r"govuk-table__cell--numeric[^>]*>([^<]+)<", row)
            result.append((kind, name.strip(), numbers))
        return result

    def test_page_loads(self):
        response, body = self.get(OVERVIEW_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<h1 class="govuk-heading-xl govuk-!-margin-bottom-4">Repository overview</h1>',
            body,
        )
        self.assertIn(
            '<p class="govuk-body">View repository totals by organisation, business unit and team.</p>',
            body,
        )
        self.assertIn(LAST_UPDATED_LINE, body)
        self.assertIn("Repository overview - GitHub Repository Stats\n</title>", body)
        crumbs = body.split('class="govuk-breadcrumbs', 1)[1].split("</nav>", 1)[0]
        self.assertIn('href="/repository-stats/">GitHub Repository Stats</a>', crumbs)
        headers = re.findall(
            r'<th scope="col" class="govuk-table__header[^"]*">([^<]+)</th>', body
        )
        self.assertEqual(
            headers,
            [
                "Organisation / business unit / team",
                "Total",
                "Public",
                "Internal",
                "Private",
            ],
        )
        hint = (
            '<p class="govuk-body-s">Select an organisation to see its business units, '
            "then select a business unit to see its teams.</p>"
        )
        self.assertIn(hint, body)
        self.assertLess(body.index(LAST_UPDATED_LINE), body.index(hint))
        self.assertLess(body.index(hint), body.index('id="repository-overview"'))

    def test_notes_under_table_removed(self):
        _, body = self.get(f"{OVERVIEW_URL}?open={ORG}&open={ORG}/HMPPS")
        self.assertNotIn("Totals include archived", body)
        self.assertNotIn("counted under each one", body)
        after_table = body.split("</table>", 1)[1].split("</main>", 1)[0]
        self.assertNotIn("<p", after_table)

    def test_organisations_collapsed_by_default(self):
        _, body = self.get(OVERVIEW_URL)
        self.assertEqual(
            self.rows(body),
            [
                ("all", "All organisations", ["34", "3", "31", "0"]),
                ("org", ORG, ["33", "2", "31", "0"]),
                ("org", OTHER_ORG, ["1", "1", "0", "0"]),
            ],
        )
        self.assertIn(
            f'<a class="govuk-link app-overview-toggle" href="{OVERVIEW_URL}?open={ORG}#overview-{ORG}">{ORG}'
            '<span class="govuk-visually-hidden"> (show business units)</span></a>',
            body,
        )
        self.assertIn(f'id="overview-{ORG}"', body)

    def test_open_organisation_shows_business_units(self):
        _, body = self.get(f"{OVERVIEW_URL}?open={ORG}&open=not-an-org")
        self.assertEqual(
            self.rows(body),
            [
                ("all", "All organisations", ["34", "3", "31", "0"]),
                ("org", ORG, ["33", "2", "31", "0"]),
                ("group-label", "Business unit", []),
                ("business-unit", "HMPPS", ["1", "0", "1", "0"]),
                ("business-unit", "Office of the CTO", ["1", "1", "0", "0"]),
                ("business-unit", "Unknown", ["31", "1", "30", "0"]),
                ("org", OTHER_ORG, ["1", "1", "0", "0"]),
            ],
        )
        self.assertIn(
            f'app-overview-toggle--open" href="{OVERVIEW_URL}#overview-{ORG}">{ORG}'
            '<span class="govuk-visually-hidden"> (hide business units)</span>',
            body,
        )
        self.assertIn(
            f'href="{OVERVIEW_URL}?open={ORG}&amp;open={OTHER_ORG}#overview-{OTHER_ORG}"',
            body,
        )
        self.assertNotIn("not-an-org", body)
        self.assertNotIn("counted under each one", body)

    def test_shared_business_unit_counts_under_each(self):
        with patch.object(
            FakeOwnership,
            "business_units_by_repository",
            lambda _self: {"asset-alpha": ["HMPPS", "Office of the CTO"]},
        ):
            _, body = self.get(f"{OVERVIEW_URL}?open={ORG}")
        self.assertNotIn("counted under each one", body)
        rows = self.rows(body)
        self.assertIn(("business-unit", "HMPPS", ["1", "1", "0", "0"]), rows)
        self.assertIn(
            ("business-unit", "Office of the CTO", ["1", "1", "0", "0"]), rows
        )

    def test_business_units_are_expandable(self):
        _, body = self.get(f"{OVERVIEW_URL}?open={ORG}")
        hmpps = f"{OVERVIEW_URL}?open={ORG}&amp;open={ORG}%2FHMPPS#overview-{ORG}-hmpps"
        self.assertIn(
            f'<a class="govuk-link app-overview-toggle" href="{hmpps}">HMPPS'
            '<span class="govuk-visually-hidden"> (show teams)</span></a>',
            body,
        )
        self.assertIn(f'id="overview-{ORG}-office-of-the-cto"', body)
        # "Business unit" once, above the group, not under every business unit.
        self.assertEqual(body.count(">Business unit</td>"), 1)
        self.assertIn(
            '<tr class="govuk-table__row app-overview-row--group-label">\n'
            '                  <td class="govuk-table__cell app-overview-group-label '
            'app-overview-group-label--business-unit" colspan="5">Business unit</td>',
            body,
        )
        self.assertNotIn("app-overview-caption", body)
        self.assertNotIn(">Team</td>", body)
        self.assertNotIn("app-overview-row--team", body)
        # Totals are bold on organisation and business unit rows.
        bu_row = body.split(f'id="overview-{ORG}-hmpps"', 1)[1].split("</tr>", 1)[0]
        self.assertIn('govuk-table__cell--numeric app-overview-strong">1</td>', bu_row)

    def test_open_business_unit_shows_teams(self):
        _, body = self.get(
            f"{OVERVIEW_URL}?open={ORG}&open={ORG}/Office of the CTO"
            f"&open={ORG}/Unknown&open={OTHER_ORG}/Unknown&open={ORG}/Not a unit"
        )
        self.assertEqual(
            self.rows(body),
            [
                ("all", "All organisations", ["34", "3", "31", "0"]),
                ("org", ORG, ["33", "2", "31", "0"]),
                ("group-label", "Business unit", []),
                ("business-unit", "HMPPS", ["1", "0", "1", "0"]),
                ("business-unit", "Office of the CTO", ["1", "1", "0", "0"]),
                ("group-label", "Team", []),
                ("team", "platform-team", ["1", "1", "0", "0"]),
                ("team", "service-team", ["1", "1", "0", "0"]),
                ("business-unit", "Unknown", ["31", "1", "30", "0"]),
                ("group-label", "Team", []),
                ("team", "No team", ["31", "1", "30", "0"]),
                ("org", OTHER_ORG, ["1", "1", "0", "0"]),
            ],
        )
        self.assertIn(
            f'<a class="govuk-link" href="https://github.com/orgs/{ORG}/teams/platform-team"'
            ' target="_blank" rel="noopener noreferrer">platform-team'
            '<span class="govuk-visually-hidden"> (opens in new tab)</span></a>',
            body,
        )
        self.assertNotIn("github.com/orgs/ministryofjustice/teams/No", body)
        self.assertIn(
            'app-overview-row--business-unit app-overview-row--expanded"', body
        )
        # Closing a business unit keeps the organisation and other units open.
        self.assertIn(
            f'app-overview-toggle--open" href="{OVERVIEW_URL}?open={ORG}'
            f"&amp;open={ORG}%2FUnknown#overview-{ORG}-office-of-the-cto"
            '">Office of the CTO',
            body,
        )
        # Closing the organisation closes its business units too.
        self.assertIn(
            f'app-overview-toggle--open" href="{OVERVIEW_URL}#overview-{ORG}">{ORG}',
            body,
        )
        self.assertNotIn("Not a unit", body)

    def test_business_unit_needs_its_organisation_open(self):
        _, body = self.get(f"{OVERVIEW_URL}?open={ORG}/HMPPS")
        self.assertEqual(
            [kind for kind, _, _ in self.rows(body)], ["all", "org", "org"]
        )
        self.assertIn(f'href="{OVERVIEW_URL}?open={ORG}#overview-{ORG}"', body)

    def test_repository_with_several_teams_counts_under_each(self):
        with (
            patch.object(
                FakeOwnership,
                "teams_by_repository",
                lambda _self: teams_by_name(
                    {
                        "asset-alpha": ["platform-team"],
                        "sample-repo-00": ["platform-team", "service-team"],
                    }
                ),
            ),
            patch.object(
                FakeOwnership,
                "business_units_by_repository",
                lambda _self: {"asset-alpha": ["HMPPS"], "sample-repo-00": ["HMPPS"]},
            ),
        ):
            _, body = self.get(f"{OVERVIEW_URL}?open={ORG}&open={ORG}/HMPPS")
        rows = self.rows(body)
        self.assertIn(("business-unit", "HMPPS", ["2", "1", "1", "0"]), rows)
        self.assertIn(("team", "platform-team", ["2", "1", "1", "0"]), rows)
        self.assertIn(("team", "service-team", ["1", "0", "1", "0"]), rows)

    def test_teams_collected_by_the_scan_job_show_display_names(self):
        with patch.object(
            FakeOwnership,
            "teams_by_repository",
            lambda _self: RepositoryTeams(
                by_github_id={200: [Team("platform-team", "Platform team")]}
            ),
        ):
            _, body = self.get(
                f"{OVERVIEW_URL}?open={ORG}&open={ORG}/Office of the CTO"
            )
        self.assertIn(("team", "Platform team", ["1", "1", "0", "0"]), self.rows(body))
        self.assertIn(
            f'href="https://github.com/orgs/{ORG}/teams/platform-team" target="_blank"'
            ' rel="noopener noreferrer">Platform team<span',
            body,
        )

    def test_organisation_display_names_keep_login_links(self):
        self.repository.display_names = {
            ORG: "Example Justice",
            OTHER_ORG: "Analytical Example",
        }
        _, body = self.get(f"{OVERVIEW_URL}?open={ORG}&open={ORG}/Office of the CTO")
        rows = self.rows(body)
        # Sorted by display name.
        self.assertEqual(
            [name for kind, name, _ in rows if kind == "org"],
            ["Analytical Example", "Example Justice"],
        )
        self.assertIn(
            f'app-overview-toggle--open" href="{OVERVIEW_URL}#overview-{ORG}">'
            "Example Justice",
            body,
        )
        self.assertIn(f'id="overview-{ORG}"', body)
        self.assertIn(f'id="overview-{ORG}-office-of-the-cto"', body)
        self.assertIn(f"https://github.com/orgs/{ORG}/teams/platform-team", body)

    def test_team_name_sits_beside_the_rule(self):
        _, body = self.get(f"{OVERVIEW_URL}?open={ORG}&open={ORG}/Office of the CTO")
        team_row = body.split("app-overview-row--team", 1)[1].split("</tr>", 1)[0]
        self.assertIn('<span class="app-overview-team-name">', team_row)
        self.assertNotIn("app-overview-team-rule", team_row)
        name_cell = team_row.split("</th>", 1)[0]
        self.assertEqual(name_cell.count("<span"), 2)

    def test_business_units_derived_from_team_access(self):
        with patch.object(
            FakeOwnership,
            "business_units_by_repository",
            lambda _self: RepositoryBusinessUnits(
                by_name={"asset-alpha": ("Office of the CTO",)},
                admin_by_github_id={5: ("HMPPS",), 200: ("HMPPS",)},
            ),
        ):
            _, body = self.get(f"{OVERVIEW_URL}?open={ORG}")
        rows = self.rows(body)
        # sample-repo-05 (internal) gets HMPPS from team access; asset-alpha keeps
        # its shared relationship result.
        self.assertIn(("business-unit", "HMPPS", ["1", "0", "1", "0"]), rows)
        self.assertIn(
            ("business-unit", "Office of the CTO", ["1", "1", "0", "0"]), rows
        )
        self.assertIn(("business-unit", "Unknown", ["31", "1", "30", "0"]), rows)

        self.repository.snapshots[SEP_25] = [
            snap(1000 + i, f"sample-bulk-{i}", "internal", SEP_25) for i in range(1234)
        ]
        _, body = self.get(OVERVIEW_URL)
        self.assertEqual(
            self.rows(body)[0],
            ("all", "All organisations", ["1,234", "0", "1,234", "0"]),
        )

    def test_group_captions_once_per_group(self):
        _, body = self.get(OVERVIEW_URL)
        self.assertNotIn("app-overview-row--group-label", body)

        _, body = self.get(
            f"{OVERVIEW_URL}?open={ORG}&open={OTHER_ORG}&open={ORG}/Office of the CTO"
            f"&open={ORG}/Unknown"
        )
        kinds = [(kind, name) for kind, name, _ in self.rows(body)]
        labels = [
            (index, name)
            for index, (kind, name) in enumerate(kinds)
            if kind == "group-label"
        ]
        # One "Business unit" line directly above each open organisation's business
        # units, and one "Team" line directly above each open business unit's teams.
        self.assertEqual(
            [name for _, name in labels],
            ["Business unit", "Team", "Team", "Business unit"],
        )
        for index, name in labels:
            expected = "business-unit" if name == "Business unit" else "team"
            self.assertEqual(kinds[index + 1][0], expected)
            self.assertIn(kinds[index - 1][0], ("org", "business-unit"))
        for kind, name in kinds:
            if kind != "group-label":
                self.assertNotIn(name, ("Business unit", "Team"))
        # A plain line spanning the table: no header cell, no bold, no toggle.
        for row in re.findall(
            r'<tr class="govuk-table__row app-overview-row--group-label">(.*?)</tr>',
            body,
            re.DOTALL,
        ):
            self.assertNotIn("<th", row)
            self.assertNotIn("<a", row)
            self.assertNotIn("app-overview-strong", row)
            self.assertIn('colspan="5"', row)

    def test_group_caption_style(self):
        with open(
            os.path.join(
                APP_DIR,
                "static/projects/repository_stats/stylesheets/visibility.css",
            )
        ) as stylesheet:
            css = stylesheet.read()
        rule = css.split(".app-overview-group-label {", 1)[1].split("}", 1)[0]
        self.assertIn("font-weight: 400;", rule)
        self.assertNotIn("background", rule)
        self.assertNotIn("text-transform", rule)
        self.assertNotIn(".app-overview-row--group-label", css)


class TestRepositoryOverviewTeamScrollBoxes(RepositoryStatsTestCase):
    def test_open_business_unit_wraps_its_teams_in_their_own_scroll_box(self):
        _, body = self.get(f"{OVERVIEW_URL}?open={ORG}&open={ORG}/Office of the CTO")
        # The team table sits inside a <td> of the outer table, in its own boxed,
        # independently-scrolling <div>, not the whole table.
        cell_start = body.index("app-overview-teambox-cell")
        after = body[cell_start:]
        div_at = after.index('<div class="app-overview-teambox">')
        table_at = after.index('<table class="govuk-table app-overview-team-table">')
        label_at = after.index(">Team</td>")
        row_at = after.index("app-overview-row--team")
        self.assertLess(div_at, table_at)
        self.assertLess(table_at, label_at)
        self.assertLess(label_at, row_at)

    def test_two_open_business_units_each_get_their_own_box(self):
        _, body = self.get(
            f"{OVERVIEW_URL}?open={ORG}&open={ORG}/Office of the CTO&open={ORG}/Unknown"
        )
        self.assertEqual(body.count('class="app-overview-teambox"'), 2)

    def test_org_and_business_unit_rows_are_outside_any_scroll_box(self):
        _, body = self.get(f"{OVERVIEW_URL}?open={ORG}&open={ORG}/Office of the CTO")
        before_box = body.split('class="app-overview-teambox"', 1)[0]
        self.assertIn(f'id="overview-{ORG}"', before_box)
        self.assertIn(f'id="overview-{ORG}-office-of-the-cto"', before_box)

    def test_outer_and_team_tables_share_matching_column_widths(self):
        with open(
            os.path.join(
                APP_DIR,
                "static/projects/repository_stats/stylesheets/visibility.css",
            )
        ) as stylesheet:
            css = stylesheet.read()
        self.assertIn(".app-overview-table,\n.app-overview-team-table {", css)
        rule = css.split(".app-overview-table,\n.app-overview-team-table {", 1)[
            1
        ].split("}", 1)[0]
        self.assertIn("table-layout: fixed;", rule)
        _, body = self.get(f"{OVERVIEW_URL}?open={ORG}&open={ORG}/Office of the CTO")
        self.assertEqual(
            body.count('<col class="app-overview-col--name">'), 2
        )  # one outer table, one open business unit's team table


class TestRepositoryOverviewStickyHeader(RepositoryStatsTestCase):
    def test_table_header_is_sticky_within_scroll_container(self):
        with open(
            os.path.join(
                APP_DIR,
                "static/projects/repository_stats/stylesheets/visibility.css",
            )
        ) as stylesheet:
            css = stylesheet.read()
        rule = css.split(".app-table-scroll thead.govuk-table__head th {", 1)[1].split(
            "}", 1
        )[0]
        self.assertIn("position: sticky;", rule)
        self.assertIn("top: 0;", rule)
        self.assertIn("background-color:", rule)

    def test_overview_drops_its_overflow_ancestor_at_normal_widths(self):
        # position: sticky breaks the moment any ancestor's overflow is anything
        # but visible, so the overview page's own scroll wrapper has to cancel the
        # shared .app-table-scroll's overflow-x: auto at normal widths, keeping it
        # only as a narrow-screen fallback (where five columns might not fit).
        with open(
            os.path.join(
                APP_DIR,
                "static/projects/repository_stats/stylesheets/visibility.css",
            )
        ) as stylesheet:
            css = stylesheet.read()
        rule = css.split(".app-table-scroll--overview {", 1)[1].split("}", 1)[0]
        self.assertIn("overflow-x: visible;", rule)
        self.assertNotIn("max-height:", rule)
        narrow_rule = css.split("@media (max-width: 40.0625em) {", 1)[1].split("}", 1)[
            0
        ]
        self.assertIn("overflow-x: auto;", narrow_rule)

    def test_overview_table_is_inside_scroll_container(self):
        _, body = self.get(OVERVIEW_URL)
        region = body.split('id="repository-overview"', 1)[0][-400:]
        self.assertIn('class="app-table-scroll app-table-scroll--overview"', region)

    def test_archived_table_still_uses_the_shared_scroll_container_only(self):
        response, body = self.get(ARCHIVED_URL)
        self.assertEqual(response.status_code, 200)
        region = body.split('id="archived-table"', 1)[0][-400:]
        self.assertIn('class="app-table-scroll"', region)
        self.assertNotIn("app-table-scroll--overview", body)


class TestRepositoryOverviewNoData(RepositoryStatsTestCase):
    repository_class = EmptyVisibilityRepository

    def test_empty_state(self):
        response, body = self.get(OVERVIEW_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn("There is no repository data yet.", body)
        self.assertNotIn('id="repository-overview"', body)


if __name__ == "__main__":
    unittest.main()
