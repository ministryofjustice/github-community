from flask import Flask

from app.main.routes.main import main
from app.main.routes.auth import auth_route
from app.main.routes.robots import robot_route
from app.main.routes.owner import owner_route
from app.main.routes.repository import repository_route


def configure_routes(app: Flask) -> None:
    app.register_blueprint(auth_route, url_prefix="/auth")
    app.register_blueprint(owner_route, url_prefix="/owner")
    app.register_blueprint(repository_route, url_prefix="/repository")
    app.register_blueprint(main)
    app.register_blueprint(robot_route)
