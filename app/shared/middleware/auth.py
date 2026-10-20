import logging
from functools import wraps
from time import time

from flask import (
    redirect,
    request,
    session,
    url_for,
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
    from app.projects.repository_stats.routes.main import render_no_access

    return render_no_access()


def _render_stats_unavailable(retry_href):
    from app.projects.repository_stats.routes.main import render_github_problem

    return render_github_problem("unavailable", 503, retry_href=retry_href)


def requires_stats_access(function_f=None, *, team=None, render_no_access=None):
    """Only let members of a GitHub team through; everyone else sees a no-access page.

    Use under @requires_auth, either bare (@requires_stats_access) to check the team in
    GITHUB_STATS_ACCESS_TEAM, or with team="org/team-slug" so a report can use its own
    team. With no team configured, or AUTH_ENABLED=false, everyone has access.

    Someone who hasn't confirmed their GitHub account yet is sent straight to GitHub to
    sign in and brought back here afterwards. The no-access and "try again later"
    pages are rendered in place (not a redirect), so the URL stays the page requested.
    """
    from app.projects.repository_stats.services.github_sign_in import safe_next_path
    from app.projects.repository_stats.services.visibility_access import (
        StatsAccess,
        check_stats_access,
    )

    def decorator(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            if not app_config.auth_enabled:
                return view(*args, **kwargs)
            access = check_stats_access(session.get("user"), team=team)
            if access is StatsAccess.ALLOWED:
                return view(*args, **kwargs)
            next_path = safe_next_path(request.full_path)
            if access is StatsAccess.NEEDS_GITHUB:
                return redirect(
                    url_for("repository_stats_main.github_login", next=next_path)
                )
            if access is StatsAccess.UNAVAILABLE:
                return _render_stats_unavailable(next_path or request.path)
            return (render_no_access or _render_stats_no_access)()

        return decorated

    return decorator(function_f) if function_f is not None else decorator
