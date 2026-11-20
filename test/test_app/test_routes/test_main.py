import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

from app.projects.repository_standards.routes.main import repository_standards_main
from app.projects.repository_standards.services.repository_compliance_service import (
    RepositoryComplianceService,
)


class TestOwnerRoutes(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.testing = True
        app.secret_key = "test"
        app.register_blueprint(
            repository_standards_main, url_prefix="/repository-standards"
        )
        self.client = app.test_client()
        self.owner_service = Mock()
        self.owner_service.find_by_id.return_value = SimpleNamespace(
            id=12, name="Team", config=SimpleNamespace(teams=["example-team"])
        )
        self.compliance_service = Mock()
        self.compliance_service.get_all_repositories.return_value = []
        for patcher in (
            patch("app.shared.middleware.auth.app_config.auth_enabled", False),
            patch(
                "app.projects.repository_standards.routes.main.get_owner_service",
                return_value=self.owner_service,
            ),
            patch(
                "app.projects.repository_standards.routes.main.get_repository_compliance_service",
                return_value=self.compliance_service,
            ),
            patch(
                "app.projects.repository_standards.routes.main.get_relationships_service"
            ),
            patch(
                "app.projects.repository_standards.routes.main.render_template",
                return_value="Owner page",
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_invalid_owner_paths_do_not_reach_the_database(self):
        for owner_id in (
            "not-an-id",
            "12.5",
            "-1",
            "0",
            "2147483648",
            "9" * 40,
            "9" * 5000,
        ):
            for method, suffix in (
                ("GET", f"/teams/{owner_id}"),
                ("GET", f"/business-units/{owner_id}"),
                ("GET", f"/teams/{owner_id}/edit"),
                ("POST", f"/teams/{owner_id}/edit"),
                ("POST", f"/teams/{owner_id}/delete"),
            ):
                with self.subTest(method=method, suffix=suffix):
                    response = self.client.open(
                        f"/repository-standards{suffix}", method=method
                    )
                    self.assertEqual(response.status_code, 404)
        self.owner_service.find_by_id.assert_not_called()
        self.owner_service.update_by_id.assert_not_called()
        self.owner_service.delete_by_id.assert_not_called()
        self.compliance_service.get_all_repositories.assert_not_called()

    def test_existing_owner_pages_use_integer_ids_and_missing_owners_still_404(self):
        for suffix in ("/teams/12", "/business-units/12", "/teams/12/edit"):
            with self.subTest(suffix=suffix):
                response = self.client.get(f"/repository-standards{suffix}")
                self.assertEqual(response.status_code, 200)
                self.owner_service.find_by_id.assert_called_with(12)
        self.owner_service.find_by_id.return_value = None
        for method, suffix in (
            ("GET", "/teams/99"),
            ("GET", "/business-units/99"),
            ("GET", "/teams/99/edit"),
            ("POST", "/teams/99/edit"),
            ("POST", "/teams/99/delete"),
        ):
            with self.subTest(method=method, suffix=suffix):
                response = self.client.open(
                    f"/repository-standards{suffix}", method=method
                )
                self.assertEqual(response.status_code, 404)
                self.owner_service.find_by_id.assert_called_with(99)

    def test_largest_database_owner_id_reaches_the_lookup(self):
        response = self.client.get("/repository-standards/teams/2147483647")
        self.assertEqual(response.status_code, 200)
        self.owner_service.find_by_id.assert_called_once_with(2147483647)

    def test_numeric_team_edit_and_delete_still_redirect_to_existing_pages(self):
        response = self.client.post(
            "/repository-standards/teams/12/edit",
            data={"name": "Team", "teams": "example-team"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/repository-standards/teams/12")
        self.owner_service.update_by_id.assert_called_once_with(
            12, "Team", ["example-team"]
        )
        response = self.client.post("/repository-standards/teams/12/delete")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/repository-standards/teams")
        self.owner_service.delete_by_id.assert_called_once_with(12)

    def test_add_team_is_not_treated_as_an_owner_id(self):
        response = self.client.get("/repository-standards/teams/add-team")
        self.assertEqual(response.status_code, 200)
        self.owner_service.find_by_id.assert_not_called()

    def test_numeric_owner_routes_still_require_sign_in(self):
        with patch("app.shared.middleware.auth.app_config.auth_enabled", True):
            for method, suffix in (
                ("GET", "/teams/12"),
                ("GET", "/business-units/12"),
                ("GET", "/teams/12/edit"),
                ("POST", "/teams/12/edit"),
                ("POST", "/teams/12/delete"),
            ):
                with self.subTest(method=method, suffix=suffix):
                    response = self.client.open(
                        f"/repository-standards{suffix}", method=method
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.location, "/auth/login")
        self.owner_service.find_by_id.assert_not_called()
        self.owner_service.update_by_id.assert_not_called()
        self.owner_service.delete_by_id.assert_not_called()


class TestLegacyPublicRepositoryScope(unittest.TestCase):
    def test_legacy_reports_query_only_public_moj_repositories(self):
        asset_service = Mock()
        asset_service.get_all_repositories.return_value = []
        service = RepositoryComplianceService(asset_service=asset_service)

        self.assertEqual(service.get_all_repositories(), [])

        asset_service.get_all_repositories.assert_called_once_with(
            organisation="ministryofjustice", visibility="public"
        )


class TestAggregateOwnerCounts(unittest.TestCase):
    def test_aggregates_counts_by_owner_and_maturity(self):
        service = RepositoryComplianceService(asset_service=SimpleNamespace())
        entities = [
            SimpleNamespace(id="team-a", name="Team A", type=SimpleNamespace(name="TEAM")),
            SimpleNamespace(id="team-b", name="Team B", type=SimpleNamespace(name="TEAM")),
            SimpleNamespace(id="team-c", name="Team C", type=SimpleNamespace(name="TEAM")),
        ]

        repositories = [
            SimpleNamespace(
                maturity_level=1,
                authoritative_team_owners=["Team A", "Team B"],
            ),
            SimpleNamespace(
                maturity_level=2,
                authoritative_team_owners=["Team A", "Team A"],
            ),
            SimpleNamespace(
                maturity_level=3,
                authoritative_team_owners=["Team B", "Unknown Team"],
            ),
            SimpleNamespace(
                maturity_level=0,
                authoritative_team_owners=["Team A"],
            ),
        ]

        service.get_all_repositories = lambda: repositories

        result = service.aggregate_owner_counts(entities)

        self.assertEqual(
            result["team-a"],
            {
                "repo_count": 3,
                "baseline_compliant_count": 2,
                "standard_compliant_count": 1,
                "exemplar_compliant_count": 0,
            },
        )
        self.assertEqual(
            result["team-b"],
            {
                "repo_count": 2,
                "baseline_compliant_count": 2,
                "standard_compliant_count": 1,
                "exemplar_compliant_count": 1,
            },
        )
        self.assertEqual(
            result["team-c"],
            {
                "repo_count": 0,
                "baseline_compliant_count": 0,
                "standard_compliant_count": 0,
                "exemplar_compliant_count": 0,
            },
        )

    def test_supports_different_owner_field_names(self):
        service = RepositoryComplianceService(asset_service=SimpleNamespace())
        entities = [
            SimpleNamespace(
                id="bu-a",
                name="Business Unit A",
                type=SimpleNamespace(name="BUSINESS_UNIT"),
            )
        ]
        repositories = [
            SimpleNamespace(
                maturity_level=3,
                authoritative_business_unit_owners=["Business Unit A"],
            )
        ]

        service.get_all_repositories = lambda: repositories

        result = service.aggregate_owner_counts(entities)

        self.assertEqual(
            result["bu-a"],
            {
                "repo_count": 1,
                "baseline_compliant_count": 1,
                "standard_compliant_count": 1,
                "exemplar_compliant_count": 1,
            },
        )
