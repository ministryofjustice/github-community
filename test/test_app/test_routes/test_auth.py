import unittest
from unittest.mock import MagicMock, patch

from authlib.integrations.base_client.errors import MismatchingStateError
from flask import Flask

from app.shared.routes.auth import auth_route


class TestAuthCallback(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test-secret"
        self.app.config["TESTING"] = True
        self.app.register_blueprint(auth_route, url_prefix="/auth")
        self.client = self.app.test_client()

    @patch("app.shared.routes.auth.auth0_service")
    def test_callback_redirects_to_login_on_mismatching_state_error(
        self, mock_auth0_service: MagicMock
    ):
        mock_auth0_service.get_access_token.side_effect = MismatchingStateError(
            "mismatching_state", "CSRF Warning! State not equal in request and response."
        )

        response = self.client.get("/auth/callback")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.headers["Location"])

    @patch("app.shared.routes.auth.auth0_service")
    def test_callback_clears_session_on_mismatching_state_error(
        self, mock_auth0_service: MagicMock
    ):
        mock_auth0_service.get_access_token.side_effect = MismatchingStateError(
            "mismatching_state", "CSRF Warning! State not equal in request and response."
        )

        with self.client.session_transaction() as sess:
            sess["user"] = {"name": "test"}
            sess["post_auth_redirect_path"] = "/some/path"

        self.client.get("/auth/callback")

        with self.client.session_transaction() as sess:
            self.assertNotIn("user", sess)
            self.assertNotIn("post_auth_redirect_path", sess)

    @patch("app.shared.routes.auth.auth0_service")
    def test_callback_redirects_to_root_on_success(
        self, mock_auth0_service: MagicMock
    ):
        mock_auth0_service.get_access_token.return_value = {"sub": "user123"}

        response = self.client.get("/auth/callback")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    @patch("app.shared.routes.auth.auth0_service")
    def test_callback_redirects_to_post_auth_path_on_success(
        self, mock_auth0_service: MagicMock
    ):
        mock_auth0_service.get_access_token.return_value = {"sub": "user123"}

        with self.client.session_transaction() as sess:
            sess["post_auth_redirect_path"] = "/some/path"

        response = self.client.get("/auth/callback")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/some/path")


if __name__ == "__main__":
    unittest.main()
