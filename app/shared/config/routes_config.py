from flask import Flask

from app.shared.routes.main import main
from app.shared.routes.auth import auth_route
from app.shared.routes.robots import robot_route
from app.projects.repository_standards.routes.owner import owner_route
from app.projects.repository_standards.routes.repository import repository_route
from app.projects.repository_standards.routes.main import repository_standards_main
from app.projects.repository_standards.routes.api import repository_standards_api


def configure_routes(app: Flask) -> None:
    app.register_blueprint(auth_route, url_prefix="/auth")
    app.register_blueprint(main)
    app.register_blueprint(robot_route)

    app.register_blueprint(
        repository_standards_main, url_prefix="/repository-standards/"
    )
    app.register_blueprint(owner_route, url_prefix="/repository-standards/owner")
    app.register_blueprint(
        repository_route, url_prefix="/repository-standards/repository"
    )
    app.register_blueprint(
        repository_standards_api, url_prefix="/repository-standards/api"
    )
