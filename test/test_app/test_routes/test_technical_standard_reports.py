import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.projects.repository_standards.routes.api import repository_standards_api
from app.projects.repository_standards.routes.main import repository_standards_main
from app.projects.repository_standards.routes.technical_standard import (
    technical_standard,
)
from app.shared.config.jinja_config import configure_jinja


def make_report(name, compliant, business_units=None, teams=None):
    return SimpleNamespace(
        name=name,
        compliant=compliant,
        checks=[],
        description=None,
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
            ),
            make_report("repo-two", False),
        ]
        self.service = SimpleNamespace(
            get_all_repositories=lambda: self.repositories,
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