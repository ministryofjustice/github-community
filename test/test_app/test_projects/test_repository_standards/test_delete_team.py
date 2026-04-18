import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask, session

from app.projects.repository_standards.routes.main import delete_team, edit_team


class TestDeleteTeamRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test-secret-key"

    @patch("app.shared.middleware.auth.app_config.auth_enabled", False)
    @patch("app.projects.repository_standards.routes.main.get_owner_service")
    @patch("app.projects.repository_standards.routes.main.get_relationships_service")
    @patch("app.projects.repository_standards.routes.main.render_template")
    def test_edit_team_get_generates_delete_csrf_token(
        self,
        mock_render_template: MagicMock,
        mock_get_relationships_service: MagicMock,
        mock_get_owner_service: MagicMock,
    ):
        mock_get_relationships_service.return_value = MagicMock()
        mock_get_owner_service.return_value.find_by_id.return_value = SimpleNamespace(
            id=9,
            name="My Team",
            config=SimpleNamespace(teams=["my-team"]),
        )
        mock_render_template.return_value = "ok"

        with self.app.test_request_context(
            "/repository-standards/teams/9/edit", method="GET"
        ):
            response = edit_team("9")

            self.assertEqual(response, "ok")
            kwargs = mock_render_template.call_args.kwargs
            csrf_token = kwargs["delete_team_csrf_token"]
            self.assertTrue(csrf_token)
            self.assertEqual(session.get("delete_team_csrf_token_9"), csrf_token)

    @patch("app.shared.middleware.auth.app_config.auth_enabled", False)
    @patch("app.projects.repository_standards.routes.main.get_owner_service")
    @patch("app.projects.repository_standards.routes.main.url_for")
    def test_delete_team_rejects_invalid_csrf(
        self,
        mock_url_for: MagicMock,
        mock_get_owner_service: MagicMock,
    ):
        mock_url_for.return_value = "/repository-standards/teams"
        owner_service = mock_get_owner_service.return_value
        owner_service.find_by_id.return_value = SimpleNamespace(id=9, type="TEAM")

        with self.app.test_request_context(
            "/repository-standards/teams/9/delete",
            method="POST",
            data={"csrf_token": "invalid-token"},
        ):
            session["delete_team_csrf_token_9"] = "valid-token"
            response = delete_team("9")

            self.assertEqual(response, ("Forbidden", 403))
            owner_service.delete_by_id.assert_not_called()

    @patch("app.shared.middleware.auth.app_config.auth_enabled", False)
    @patch("app.projects.repository_standards.routes.main.get_owner_service")
    def test_delete_team_rejects_non_team_owner(
        self,
        mock_get_owner_service: MagicMock,
    ):
        owner_service = mock_get_owner_service.return_value
        owner_service.find_by_id.return_value = SimpleNamespace(
            id=9,
            type="BUSINESS_UNIT",
        )

        with self.app.test_request_context(
            "/repository-standards/teams/9/delete",
            method="POST",
            data={"csrf_token": "token"},
        ):
            session["delete_team_csrf_token_9"] = "token"
            response = delete_team("9")

            self.assertEqual(response, ("Owner not found", 404))
            owner_service.delete_by_id.assert_not_called()

    @patch("app.shared.middleware.auth.app_config.auth_enabled", False)
    @patch("app.projects.repository_standards.routes.main.get_owner_service")
    def test_delete_team_rejects_owner_with_non_team_type(
        self,
        mock_get_owner_service: MagicMock,
    ):
        owner_service = mock_get_owner_service.return_value
        owner_service.find_by_id.return_value = SimpleNamespace(id=9, type="USER")

        with self.app.test_request_context(
            "/repository-standards/teams/9/delete",
            method="POST",
            data={"csrf_token": "token"},
        ):
            session["delete_team_csrf_token_9"] = "token"
            response = delete_team("9")

            self.assertEqual(response, ("Owner not found", 404))
            owner_service.delete_by_id.assert_not_called()

    @patch("app.shared.middleware.auth.app_config.auth_enabled", False)
    @patch("app.projects.repository_standards.routes.main.get_owner_service")
    @patch("app.projects.repository_standards.routes.main.url_for")
    def test_delete_team_deletes_team_with_valid_csrf(
        self,
        mock_url_for: MagicMock,
        mock_get_owner_service: MagicMock,
    ):
        mock_url_for.return_value = "/repository-standards/teams"
        owner_service = mock_get_owner_service.return_value
        owner_service.find_by_id.return_value = SimpleNamespace(id=9, type="TEAM")
        owner_service.delete_by_id.return_value = True

        with self.app.test_request_context(
            "/repository-standards/teams/9/delete",
            method="POST",
            data={"csrf_token": "valid-token"},
        ):
            session["delete_team_csrf_token_9"] = "valid-token"
            response = delete_team("9")

            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, "/repository-standards/teams")
            owner_service.delete_by_id.assert_called_once_with("9")
            self.assertIsNone(session.get("delete_team_csrf_token_9"))


if __name__ == "__main__":
    unittest.main()
