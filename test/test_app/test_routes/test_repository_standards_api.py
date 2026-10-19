import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

from app.projects.repository_standards.routes.api import repository_standards_api


class TestRepositoryStandardsBadgeRoute(unittest.TestCase):
    def test_existing_badge_url_uses_new_standard_and_keeps_style(self):
        app = Flask(__name__)
        app.register_blueprint(
            repository_standards_api, url_prefix="/repository-standards/api"
        )
        technical_standard_service = SimpleNamespace(
            get_repository_by_name=lambda name: SimpleNamespace(compliant=True)
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
            get_repository_by_name=lambda name: None
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