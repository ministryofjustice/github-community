import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

from app.projects.repository_standards.routes.api import repository_standards_api
from app.projects.repository_standards.routes.deprecated import repository_standards_deprecated


class TestRepositoryStandardsBadgeRoute(unittest.TestCase):
    def test_org_qualified_badge_looks_up_the_requested_org(self):
        app = Flask(__name__)
        app.register_blueprint(repository_standards_api, url_prefix="/repository-standards/api")
        service = Mock()
        service.get_repository_by_name.return_value = SimpleNamespace(compliant=False)
        with (
            patch("app.projects.repository_standards.routes.api.get_technical_standard_service", return_value=service),
            patch("app.projects.repository_standards.routes.api.requests.get", return_value=SimpleNamespace(
                content=b"badge-image", headers={"content-type": "image/svg+xml"}
            )),
        ):
            response = app.test_client().get(
                "/repository-standards/api/moj-analytical-services/shared/badge"
            )
        self.assertEqual(response.status_code, 200)
        service.get_repository_by_name.assert_called_once_with("shared", "moj-analytical-services")

    def test_existing_badge_url_uses_new_standard_and_keeps_style(self):
        app = Flask(__name__)
        app.register_blueprint(
            repository_standards_api, url_prefix="/repository-standards/api"
        )
        technical_standard_service = SimpleNamespace(
            get_repository_by_name=lambda name, organisation: SimpleNamespace(compliant=True)
        )
        shields_response = SimpleNamespace(
            content=b"badge-image",
            headers={"content-type": "image/svg+xml"},
        )

        with (
            patch(
                "app.projects.repository_standards.routes.api.get_technical_standard_service",
                return_value=technical_standard_service,
            ),
            patch(
                "app.projects.repository_standards.routes.api.requests.get",
                return_value=shields_response,
            ) as shields_get,
        ):
            response = app.test_client().get(
                "/repository-standards/api/example-repo/badge?style=flat"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"badge-image")
        self.assertEqual(response.content_type, "image/svg+xml")
        self.assertIn("/badge/MOJ-COMPLIANT-cce2d8", shields_get.call_args.args[0])
        self.assertIn("style=flat", shields_get.call_args.args[0])

    def test_missing_repository_gets_neutral_badge(self):
        app = Flask(__name__)
        app.register_blueprint(
            repository_standards_api, url_prefix="/repository-standards/api"
        )
        technical_standard_service = SimpleNamespace(
            get_repository_by_name=lambda name, organisation: None
        )
        shields_response = SimpleNamespace(
            content=b"badge-image",
            headers={"content-type": "image/svg+xml"},
        )

        with (
            patch(
                "app.projects.repository_standards.routes.api.get_technical_standard_service",
                return_value=technical_standard_service,
            ),
            patch(
                "app.projects.repository_standards.routes.api.requests.get",
                return_value=shields_response,
            ) as shields_get,
        ):
            response = app.test_client().get(
                "/repository-standards/api/missing-repo/badge"
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("/badge/MOJ-NOT%20FOUND-b1b4b6", shields_get.call_args.args[0])


class TestLegacyBadgeCompatibility(unittest.TestCase):
    def test_legacy_badge_urls_return_the_new_moj_standard_result(self):
        app = Flask(__name__)
        app.register_blueprint(repository_standards_deprecated)
        service = Mock()
        service.get_repository_by_name.return_value = SimpleNamespace(compliant=True)
        paths = (
            "/api/v1/compliant_public_repositories/example-repo",
            "/api/v1/compliant_public_repositories/endpoint/example-repo",
            "/api/v2/compliant-repository/example-repo",
        )
        with patch(
            "app.projects.repository_standards.routes.deprecated.get_technical_standard_service",
            return_value=service,
        ):
            for path in paths:
                with self.subTest(path=path):
                    response = app.test_client().get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json["message"], "COMPLIANT")
                    self.assertEqual(response.json["color"], "cce2d8")
                    self.assertEqual(response.json["label"], "MOJ")
        self.assertEqual(service.get_repository_by_name.call_count, len(paths))
        service.get_repository_by_name.assert_called_with(
            "example-repo", "ministryofjustice"
        )

    def test_legacy_badge_returns_current_noncompliant_and_missing_states(self):
        app = Flask(__name__)
        app.register_blueprint(repository_standards_deprecated)
        service = Mock()
        service.get_repository_by_name.side_effect = [
            SimpleNamespace(compliant=False), None
        ]
        with patch(
            "app.projects.repository_standards.routes.deprecated.get_technical_standard_service",
            return_value=service,
        ):
            noncompliant = app.test_client().get(
                "/api/v2/compliant-repository/example-repo"
            ).json
            missing = app.test_client().get(
                "/api/v2/compliant-repository/missing-repo"
            ).json
        self.assertEqual(noncompliant["message"], "NON-COMPLIANT")
        self.assertEqual(noncompliant["color"], "f4cdc6")
        self.assertEqual(missing["message"], "NOT FOUND")
        self.assertEqual(missing["color"], "b1b4b6")