import logging
from functools import wraps

from flask import (
    redirect,
    session,
)

from app.main.config.app_config import app_config

logger = logging.getLogger(__name__)


def requires_auth(function_f):
    @wraps(function_f)
    def decorated(*args, **kwargs):
        if app_config.auth_enabled and "user" not in session:
            return redirect("/auth/login")
        return function_f(*args, **kwargs)

    return decorated
