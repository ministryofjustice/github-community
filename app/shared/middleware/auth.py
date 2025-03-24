import logging
from functools import wraps

from flask import redirect, session
from app.shared.config.app_config import app_config
from app.projects.repository_standards.services.github_service import GitHubUserService

logger = logging.getLogger(__name__)

GITHUB_ORG = "ministryofjustice"


def requires_auth(function_f):
    @wraps(function_f)
    def decorated(*args, **kwargs):
        if app_config.auth_enabled:
            if "user" not in session:
                logger.info("User not found in session, redirecting to login.")
                return redirect("/auth/login")

            user_data = session["user"]
            idp = user_data.get("idp", "").lower()
            access_token = session.get("access_token")

            # If the user logged in with GitHub, check their org membership
            if idp == "github":
                if not access_token:
                    logger.warning("GitHub login detected but no access token found.")
                    return redirect("/auth/login")

                github_service = GitHubUserService(access_token)
                if not github_service.is_user_in_organisation(GITHUB_ORG):
                    logger.warning(
                        f"User {user_data.get('nickname', 'unknown')} is not in {GITHUB_ORG}."
                    )
                    return redirect("/auth/login")

        return function_f(*args, **kwargs)

    return decorated
