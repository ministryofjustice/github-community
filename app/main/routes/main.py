import logging

from flask import Blueprint, render_template

from app.main.middleware.auth import requires_auth
from app.main.repositories.owner_repository import get_owner_repository

logger = logging.getLogger(__name__)

main = Blueprint("main", __name__)


@main.route("/", methods=["GET"])
@requires_auth
def index():
    owner_repository = get_owner_repository()
    owners = owner_repository.find_all_names()

    return render_template("pages/home.html", owners=owners)
