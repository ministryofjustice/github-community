import logging
from functools import wraps
from time import time

from flask import (
    redirect,
    request,
    session,
)

from app.shared.config.app_config import app_config

logger = logging.getLogger(__name__)


def requires_auth(function_f):
    @wraps(function_f)
    def decorated(*args, **kwargs):
        if app_config.auth_enabled and (
            "user" not in session or session["user"].get("expires_at", 0) < time()
        ):
            session.pop("user", None)
            session["post_auth_redirect_path"] = request.full_path
            return redirect("/auth/login")
        return function_f(*args, **kwargs)

    return decorated


def _render_stats_no_access():
    from flask import render_template

    from app.projects.repository_stats.config.visibility_config import (
        VISIBILITY_SLACK_CHANNEL_NAME,
        VISIBILITY_SLACK_CHANNEL_URL,
    )

    return (
        render_template(
            "projects/repository_stats/pages/no_access.html",
            slack_channel_name=VISIBILITY_SLACK_CHANNEL_NAME,
            slack_channel_url=VISIBILITY_SLACK_CHANNEL_URL,
        ),
        403,
    )


def requires_stats_access(function_f=None, *, team=None, render_no_access=None):
    """Only let members of a GitHub team through; everyone else sees a no-access page.

    Use under @requires_auth, either bare (@requires_stats_access) to check the team in
    GITHUB_STATS_ACCESS_TEAM, or with team="org/team-slug" so a report can use its own
    team. With no team configured, or AUTH_ENABLED=false, everyone has access. The no-access
    page is rendered in place (not a redirect), so the URL stays the page requested.
    """
    from app.projects.repository_stats.services.visibility_access import (
        user_has_stats_access,
    )

    def decorator(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            if app_config.auth_enabled and not user_has_stats_access(
                session.get("user"), team=team
            ):
                return (render_no_access or _render_stats_no_access)()
            return view(*args, **kwargs)

        return decorated

    return decorator(function_f) if function_f is not None else decorator
