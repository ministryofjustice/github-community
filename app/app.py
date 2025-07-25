import logging

from flask import Flask
from flask_migrate import upgrade

from app.projects.repository_standards.config.stub_data_config import create_stub_data
from app.shared.config.app_config import app_config
from app.shared.config.cors_config import configure_cors
from app.shared.config.error_handlers_config import configure_error_handlers
from app.shared.config.jinja_config import configure_jinja
from app.shared.config.limiter_config import configure_limiter
from app.shared.config.logging_config import configure_logging
from app.shared.config.routes_config import configure_routes
from app.shared.config.sentry_config import configure_sentry
from app.shared.database import db, db_migration

logger = logging.getLogger(__name__)


def create_app(is_rate_limit_enabled=True) -> Flask:
    configure_logging(app_config.logging_level)

    logger.info("Starting app...")

    app = Flask(__name__, static_folder="static", static_url_path="/assets")

    app.secret_key = app_config.flask.app_secret_key

    app.config["SQLALCHEMY_DATABASE_URI"] = app_config.postgres.sql_alchemy_database_url
    db.init_app(app)
    db_migration.init_app(app, db)

    with app.app_context():
        upgrade()

    configure_routes(app)
    configure_error_handlers(app)
    configure_limiter(app, is_rate_limit_enabled)
    configure_jinja(app)
    configure_cors(app)
    configure_sentry(app_config.sentry.dsn_key, app_config.sentry.environment)

    if app_config.add_stub_values_to_database:
        create_stub_data(app)

    logger.info("Running app...")

    return app
