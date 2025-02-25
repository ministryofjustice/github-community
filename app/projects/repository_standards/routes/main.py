import logging

from flask import Blueprint, render_template

from app.shared.middleware.auth import requires_auth
from app.projects.repository_standards.repositories.owner_repository import (
    get_owner_repository,
)

logger = logging.getLogger(__name__)

repository_standards_main = Blueprint("repository_standards_main", __name__)


@repository_standards_main.route("/", methods=["GET"])
@requires_auth
def index():
    owner_repository = get_owner_repository()
    owners = owner_repository.find_all_names()

    return render_template(
        "projects/repository_standards/pages/home.html", owners=owners
    )
