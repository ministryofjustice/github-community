import logging

from flask import Blueprint, render_template

from app.main.middleware.auth import requires_auth
from app.main.services.asset_service import get_asset_service

logger = logging.getLogger(__name__)

repository_route = Blueprint("repository_route", __name__)


@repository_route.route("/<repository_name>", methods=["GET"])
@requires_auth
def index(repository_name: str):
    asset_service = get_asset_service()

    repository = asset_service.get_repository_by_name(repository_name)

    logger.info(f"Rendering repository page for {repository.admin_owner_names}")

    return render_template(
        "pages/repository.html",
        repository=repository,
    )
