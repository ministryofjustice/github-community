from flask_admin.contrib.sqla import ModelView
from .db_models import Acronym
from ...shared.database import db


def register_admin_views(admin):
    admin.add_view(ModelView(Acronym, db.session, category="Acronyms"))