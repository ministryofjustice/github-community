import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.projects.repository_standards.models.technical_standard import (
    TechnicalStandardCheck,
    TechnicalStandardReportView,
)
from app.projects.repository_standards.routes.api import repository_standards_api
from app.projects.repository_standards.routes.main import repository_standards_main
from app.projects.repository_standards.routes.technical_standard import (
    technical_standard,
)
from app.shared.config.jinja_config import configure_jinja


def make_report(name, compliant, business_units=None, teams=None, visibility=None):
    return TechnicalStandardReportView(
        name=name,
        compliant=compliant,
        checks=[],
        description=None,
        last_updated=None,
        visibility=visibility,
        authoritative_business_unit_owners=business_units or [],
        authoritative_team_owners=teams or [],
    )


class TestTechnicalStandardReportRoutes(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test"
        configure_jinja(self.app)
        self.app.register_blueprint(
            repository_standards_main, url_prefix="/repository-standards/"
        )
        self.app.register_blueprint(
            repository_standards_api, url_prefix="/repository-standards/api"
        )
        self.app.register_blueprint(
            technical_standard,
            url_prefix="/repository-standards/technical-standard",
        )
        self.client = self.app.test_client()
        self.business_unit = SimpleNamespace(
            id=1,
            name="HMPPS",
            type="BUSINESS_UNIT",
        )
        self.team = SimpleNamespace(id=2, name="Platform Team", type="TEAM")
        self.owners = [self.business_unit, self.team]
        self.repositories = [
            make_report(
                "repo-one",
                True,
                business_units=["HMPPS"],
                teams=["Platform Team"],
                visibility="public",
            ),
            make_report("repo-two", False, visibility="private"),
        ]
        self.service = SimpleNamespace(
            get_all_repositories=lambda: self.repositories,
            get_check_summaries=lambda repositories: [],
            get_repository_by_name=lambda name: next(
                (repository for repository in self.repositories if repository.name == name),
                None,
            ),
            get_owner_counts=lambda owners: {
                owner.id: {"repo_count": 1, "compliant_count": 1}
                for owner in owners
            },
            get_repositories_for_owner=lambda owner: [self.repositories[0]],
            get_unowned_repositories=lambda: [self.repositories[1]],
        )
        self.owner_repository = SimpleNamespace(
            find_all_business_units=lambda: [self.business_unit],
            find_all_teams=lambda: [self.team],
        )
        self.owner_service = SimpleNamespace(
            find_by_id=lambda owner_id: {
                "1": self.business_unit,
                "2": self.team,
            }.get(owner_id)
        )
        self.patches = [
            patch("app.shared.middleware.auth.app_config.auth_enabled", False),
            patch(
                "app.projects.repository_standards.routes.technical_standard.get_technical_standard_service",
                return_value=self.service,
            ),
            patch(
                "app.projects.repository_standards.routes.technical_standard.get_owner_repository"
                , return_value=self.owner_repository
            ),
            patch(
                "app.projects.repository_standards.routes.technical_standard.get_owner_service"
                , return_value=self.owner_service
            ),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_main_page_links_to_all_current_standard_report_categories(self):
        response = self.client.get("/repository-standards/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("technical-standard/business-units", body)
        self.assertIn("technical-standard/teams", body)
        self.assertIn("technical-standard/unowned-repositories", body)
        self.assertIn("technical-standard/checks-overview", body)

    def test_technical_standard_home_does_not_repeat_checks_overview_link(self):
        response = self.client.get(
            "/repository-standards/technical-standard/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "technical-standard/checks-overview", response.get_data(as_text=True)
        )

    def test_checks_overview_sorts_and_displays_check_totals(self):
        self.service.get_check_summaries = lambda repositories: [
            {
                "number": 1,
                "name": "Must have an authoritative owner",
                "link_to_guidance": "https://example.test/standard#owner",
                "pass_count": 1,
                "fail_count": 1,
                "not_checked_count": 0,
                "pass_rate": 50,
            }
        ]

        response = self.client.get(
            "/repository-standards/technical-standard/checks-overview"
        )
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Compliance by requirement", body)
        self.assertIn("Must have an authoritative owner", body)
        self.assertIn('data-sort-value="1">1</td>', body)
        self.assertIn('data-sort-value="50">50%</td>', body)
        self.assertIn('aria-sort="ascending">Requirement', body)
        self.assertIn('aria-sort="none">Pass rate', body)
        self.assertNotIn(">Not checked</th>", body)

    def test_checks_overview_shows_not_checked_only_when_results_are_missing(self):
        self.service.get_check_summaries = lambda repositories: [
            {
                "number": 1,
                "name": "Must have an authoritative owner",
                "link_to_guidance": "https://example.test/standard#owner",
                "pass_count": 1,
                "fail_count": 0,
                "not_checked_count": 1,
                "pass_rate": 50,
            }
        ]

        response = self.client.get(
            "/repository-standards/technical-standard/checks-overview"
        )
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(">Not checked</th>", body)
        self.assertIn('data-sort-value="1">1</td>', body)

    def test_checks_overview_shows_empty_repository_state(self):
        self.repositories.clear()

        response = self.client.get(
            "/repository-standards/technical-standard/checks-overview"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("No repository data is available.", response.get_data(as_text=True))

    def test_assessment_guidance_route_is_removed(self):
        response = self.client.get(
            "/repository-standards/technical-standard/how-checks-are-assessed"
        )
        self.assertEqual(response.status_code, 404)

    def test_failed_checks_show_recommendations_but_passing_checks_do_not(self):
        self.repositories[0].checks = [
            TechnicalStandardCheck(
                5, "Security alerts", "fail", "Description", "/standard",
                ["Resolve High/Critical Code Scanning alerts.", "Verify <access>."],
            ),
            TechnicalStandardCheck(
                7, "Default branch", "pass", "Description", "/standard",
                ["This recommendation must not appear."],
            ),
        ]
        response = self.client.get(
            "/repository-standards/technical-standard/repositories/repo-one"
        )
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body.count("What to change"), 1)
        self.assertIn("Resolve High/Critical Code Scanning alerts.", body)
        self.assertIn("Verify &lt;access&gt;.", body)
        self.assertNotIn("This recommendation must not appear.", body)

    def test_report_without_recommendations_has_no_empty_action_lists(self):
        self.repositories[0].checks = [
            TechnicalStandardCheck(1, "Owner", "fail", "Description", "/standard")
        ]
        response = self.client.get(
            "/repository-standards/technical-standard/repositories/repo-one"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("What to change", response.get_data(as_text=True))

    def test_progress_and_snapshot_time_render_on_lists_and_detail(self):
        report = self.repositories[0]
        report.checks = [
            TechnicalStandardCheck(
                number, "Requirement", "pass" if number < 9 else "fail",
                "Description", "/standard",
            )
            for number in range(1, 10)
        ]
        report.last_updated = datetime(2026, 10, 15, 3, 24)
        for suffix in (
            "repositories", "business-units/1", "teams/2", "repositories/repo-one"
        ):
            with self.subTest(suffix=suffix):
                response = self.client.get(
                    f"/repository-standards/technical-standard/{suffix}"
                )
                self.assertEqual(response.status_code, 200)
                body = response.get_data(as_text=True)
                self.assertIn("8/9 (89%)", body)
                self.assertIn('datetime="2026-10-15T03:24:00"', body)
                self.assertIn("15 October 2026 at 03:24", body)
                if suffix == "repositories/repo-one":
                    self.assertIn("View standard", body)
                else:
                    self.assertIn('data-sort-value="88.888', body)
                    self.assertIn("Last updated:", body)
                    self.assertIn("15 October 2026 at 03:24</time>.", body)
                    self.assertNotIn("latest repository", body)

    def test_empty_list_and_unknown_snapshot_times_render(self):
        body = self.client.get(
            "/repository-standards/technical-standard/repositories/repo-one"
        ).get_data(as_text=True)
        self.assertIn("Not available", body)
        self.assertIn("0/0 (0%)", body)
        self.repositories.clear()
        response = self.client.get(
            "/repository-standards/technical-standard/repositories"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Not available", response.get_data(as_text=True))

    def test_owner_summary_routes_render(self):
        for path, owner_name in (
            ("/repository-standards/technical-standard/business-units", "HMPPS"),
            ("/repository-standards/technical-standard/teams", "Platform Team"),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertIn(owner_name, response.get_data(as_text=True))

    def test_owner_and_unowned_repository_routes_render(self):
        for path in (
            "/repository-standards/technical-standard/business-units/1",
            "/repository-standards/technical-standard/teams/2",
            "/repository-standards/technical-standard/unowned-repositories",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                body = response.get_data(as_text=True)
                expected_repository = (
                    "repo-one" if path.endswith(("/1", "/2")) else "repo-two"
                )
                self.assertIn(expected_repository, body)
                self.assertIn(
                    "/repository-standards/technical-standard/badges/", body
                )

    def test_business_unit_and_team_repository_lists_filter_visibility(self):
        self.service.get_repositories_for_owner = lambda owner: self.repositories
        for path in (
            "/repository-standards/technical-standard/business-units/1?visibility=private",
            "/repository-standards/technical-standard/teams/2?visibility=private",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                body = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn("repo-two", body)
                self.assertNotIn("repo-one", body)
                self.assertIn('<option value="private" selected>', body)
                self.assertIn("Visibility", body)
                self.assertIn("Private", body)

    def test_unowned_repository_list_filters_visibility(self):
        self.service.get_unowned_repositories = lambda: self.repositories
        response = self.client.get(
            "/repository-standards/technical-standard/unowned-repositories?visibility=public"
        )
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("repo-one", body)
        self.assertNotIn("repo-two", body)
        self.assertIn('<option value="public" selected>', body)
        self.assertIn("Public", body)

    def test_all_repositories_route_renders_local_badges(self):
        response = self.client.get(
            "/repository-standards/technical-standard/repositories"
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn(
            "/repository-standards/technical-standard/badges/compliant.svg", body
        )
        self.assertEqual(body.count("(50%)"), 2)

    def test_all_repositories_can_filter_visibility(self):
        response = self.client.get(
            "/repository-standards/technical-standard/repositories?visibility=private"
        )
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("repo-two", body)
        self.assertNotIn("repo-one", body)
        self.assertIn('id="visibility" name="visibility"', body)
        self.assertIn('<option value="private" selected>', body)
        self.assertIn("Private", body)

    def test_all_repositories_rejects_unknown_visibility_filter(self):
        response = self.client.get(
            "/repository-standards/technical-standard/repositories?visibility=secret"
        )
        self.assertEqual(response.status_code, 400)

    def test_all_repositories_can_filter_internal_visibility(self):
        self.repositories[0].visibility = "internal"
        response = self.client.get(
            "/repository-standards/technical-standard/repositories?visibility=internal"
        )
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("repo-one", body)
        self.assertNotIn("repo-two", body)
        self.assertIn("Internal", body)

    def test_empty_visibility_filter_has_clear_empty_state(self):
        response = self.client.get(
            "/repository-standards/technical-standard/repositories?visibility=internal"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("No repositories found for this visibility.", response.get_data(as_text=True))

    def test_repository_detail_shows_legacy_style_summary_and_new_badge_snippet(self):
        response = self.client.get(
            "/repository-standards/technical-standard/repositories/repo-one"
        )
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Owner", body)
        self.assertIn("HMPPS", body)
        self.assertIn("Platform Team", body)
        self.assertIn("Description", body)
        self.assertIn("Visibility", body)
        self.assertIn("Public", body)
        self.assertIn("MOJ Repository Compliance Badge", body)
        self.assertIn("/repository-standards/api/repo-one/badge", body)
        self.assertIn(
            "/repository-standards/technical-standard/repositories/repo-one",
            body,
        )

    def test_authenticated_report_badge_routes_render_compliant_and_non_compliant_svgs(self):
        for status, expected_title in (
            ("compliant", "MOJ: COMPLIANT"),
            ("non-compliant", "MOJ: NON-COMPLIANT"),
        ):
            with self.subTest(status=status):
                response = self.client.get(
                    f"/repository-standards/technical-standard/badges/{status}.svg"
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "image/svg+xml")
                self.assertIn(expected_title, response.get_data(as_text=True))
                self.assertEqual(
                    response.headers["Cache-Control"],
                    "private, max-age=60, must-revalidate",
                )

    def test_report_badge_route_rejects_unknown_status(self):
        response = self.client.get(
            "/repository-standards/technical-standard/badges/unknown.svg"
        )

        self.assertEqual(response.status_code, 404)

    def test_owner_detail_routes_reject_wrong_owner_types(self):
        response = self.client.get(
            "/repository-standards/technical-standard/business-units/2"
        )

        self.assertEqual(response.status_code, 404)