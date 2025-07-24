from flask_admin import AdminIndexView, expose
from flask import session, redirect, url_for
from app.shared.config.app_config import app_config


class SecureAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not self.is_accessible():
            return redirect('/auth/login')
        return super().index()

    def is_accessible(self):
        if not app_config.auth_enabled:
            return True
        user = session.get("user")
        return user and user.get("email") in app_config.admin_emails

    def inaccessible_callback(self, name, **kwargs):
        return redirect('/auth/login')