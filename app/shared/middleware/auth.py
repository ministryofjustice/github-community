import logging
from functools import wraps

from flask import (
    redirect,
    session,
)

from app.shared.config.app_config import app_config

logger = logging.getLogger(__name__)


def requires_auth(function_f):
    @wraps(function_f)
    def decorated(*args, **kwargs):
        if app_config.auth_enabled and "user" not in session:
            return redirect("/auth/login")
        return function_f(*args, **kwargs)

    return decorated

def requires_admin(function_f):
    @wraps(function_f)
    def decorated(*args, **kwargs):
        if app_config.auth_enabled:
            user = session.get("user")
            if not user or user.get("email") not in app_config.admin_emails:
                return redirect("/auth/login")
        return function_f(*args, **kwargs)
    return decorated
