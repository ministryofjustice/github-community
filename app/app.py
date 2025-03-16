import logging

from flask import Flask

from app.shared.config.app_config import app_config
from app.shared.config.cors_config import configure_cors
from app.shared.config.error_handlers_config import configure_error_handlers
from app.shared.config.jinja_config import configure_jinja
from app.shared.config.limiter_config import configure_limiter
from app.shared.config.logging_config import configure_logging
from app.shared.config.routes_config import configure_routes
from app.projects.repository_standards.db_models import db
from app.projects.repository_standards.repositories.owner_repository import (
    get_owner_repository,
)
from app.projects.repository_standards.services.asset_service import get_asset_service

logger = logging.getLogger(__name__)


def create_app(is_rate_limit_enabled=True) -> Flask:
    configure_logging(app_config.logging_level)

    logger.info("Starting app...")

    app = Flask(__name__, static_folder="static", static_url_path="/assets")

    app.secret_key = app_config.flask.app_secret_key

    app.config["SQLALCHEMY_DATABASE_URI"] = app_config.postgres.sql_alchemy_database_url
    db.init_app(app)
    with app.app_context():
        db.create_all()

    configure_routes(app)
    configure_error_handlers(app)
    configure_limiter(app, is_rate_limit_enabled)
    configure_jinja(app)
    configure_cors(app)

    if app_config.add_stub_values_to_database:
        create_stub_data(app)

    logger.info("Running app...")

    return app


def create_stub_data(app):
    admin_access = "STUBBED - Admin Access"
    asset_type = "STUBBED - GitHub Repository"

    with app.app_context():
        asset_service = get_asset_service()
        owner_repository = get_owner_repository()

        asset_service.clean_all_tables()

        hmpps = owner_repository.add_owner("STUBBED - HMPPS")
        opg = owner_repository.add_owner("STUBBED - OPG")
        laa = owner_repository.add_owner("STUBBED - LAA")

        operations_engineering = asset_service.add_asset(
            "operations-engineering",
            asset_type,
            data={
                "basic": {
                    "name": "operations-engineering",
                    "license": "mit",
                    "default_branch_name": "master",
                    "visibility": "public",
                    "description": "Operations Engineering repository",
                    "delete_branch_on_merge": None,
                },
                "access": {
                    "teams": [
                        "operations-engineering",
                    ],
                    "teams_parents": ["technical-architects"],
                    "teams_with_admin": [
                        "operations-engineering",
                    ],
                    "teams_with_admin_parents": ["technical-architects"],
                },
                "security_and_analysis": {
                    "advanced_security": None,
                    "non_provider_patterns": "enabled",
                    "push_protection_status": "enabled",
                    "secret_scanning_status": "enabled",
                    "secret_scanning_validity_checks": None,
                },
                "default_branch_protection": {
                    "enabled": None,
                    "enforce_admins": True,
                    "allow_force_pushes": False,
                    "required_signatures": False,
                    "dismiss_stale_reviews": True,
                    "require_code_owner_reviews": True,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 2,
                },
            },
        )
        asset_service.create_relationship(operations_engineering, hmpps, admin_access)

        opg_data = asset_service.add_asset(
            "opg-data",
            asset_type,
            data={
                "basic": {
                    "name": "opg-data",
                    "license": "mit",
                    "default_branch_name": "main",
                    "visibility": "public",
                    "description": "OPG Data repository",
                    "delete_branch_on_merge": None,
                },
                "access": {
                    "teams": [
                        "operations-engineering",
                    ],
                    "teams_parents": ["technical-architects"],
                    "teams_with_admin": [
                        "operations-engineering",
                    ],
                    "teams_with_admin_parents": ["technical-architects"],
                },
                "security_and_analysis": {
                    "advanced_security": None,
                    "non_provider_patterns": "disabled",
                    "push_protection_status": "disabled",
                    "secret_scanning_status": "enabled",
                    "secret_scanning_validity_checks": None,
                },
                "default_branch_protection": {
                    "enabled": None,
                    "enforce_admins": True,
                    "allow_force_pushes": False,
                    "required_signatures": False,
                    "dismiss_stale_reviews": True,
                    "require_code_owner_reviews": True,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 2,
                },
            },
        )
        asset_service.create_relationship(opg_data, opg, admin_access)

        cla_public = asset_service.add_asset(
            "cla_public",
            asset_type,
            data={
                "basic": {
                    "name": "cla_public",
                    "license": "mit",
                    "default_branch_name": "main",
                    "visibility": "public",
                    "description": "CLA Public repository",
                    "delete_branch_on_merge": None,
                },
                "access": {
                    "teams": [
                        "HMPPS Developers",
                    ],
                    "teams_parents": ["technical-architects"],
                    "teams_with_admin": [
                        "HMPPS Developers",
                    ],
                    "teams_with_admin_parents": ["technical-architects"],
                },
            },
        )
        asset_service.create_relationship(cla_public, laa, admin_access)
