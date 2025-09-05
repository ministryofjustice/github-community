import logging
from functools import wraps

from flask import (
    redirect,
    session,
    request,
)

from app.shared.config.app_config import app_config

logger = logging.getLogger(__name__)


def requires_auth(function_f):
    @wraps(function_f)
    def decorated(*args, **kwargs):
        if app_config.auth_enabled and "user" not in session:
            session["post_auth_redirect_path"] = request.full_path
            return redirect("/auth/login")
        return function_f(*args, **kwargs)

    return decorated
