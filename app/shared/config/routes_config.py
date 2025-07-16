from flask import Flask

from app.projects.repository_standards.routes.api import repository_standards_api
from app.projects.repository_standards.routes.deprecated import (
    repository_standards_deprecated,
)
from app.projects.repository_standards.routes.main import repository_standards_main
from app.projects.acronyms.routes.main import acronyms_main
from app.shared.routes.auth import auth_route
from app.shared.routes.main import main
from app.shared.routes.robots import robot_route


def configure_routes(app: Flask) -> None:
    app.register_blueprint(auth_route, url_prefix="/auth")
    app.register_blueprint(main)
    app.register_blueprint(robot_route)

    app.register_blueprint(
        repository_standards_main, url_prefix="/repository-standards/"
    )
    app.register_blueprint(
        repository_standards_api, url_prefix="/repository-standards/api"
    )
    app.register_blueprint(repository_standards_deprecated, url_prefix="/")

    app.register_blueprint(
        acronyms_main, url_prefix="/acronyms/"
    )
