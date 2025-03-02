import logging

from flask import Blueprint, render_template
from typing import List
from app.projects.repository_standards.repositories.asset_repository import AssetView
from app.projects.repository_standards.services.asset_service import AssetService
from app.projects.repository_standards.services.asset_service import get_asset_service
from app.shared.middleware.auth import requires_auth
from app.projects.repository_standards.routes.api import get_compliance_status

logger = logging.getLogger(__name__)

repository_standards_main = Blueprint("repository_standards_main", __name__)


def decorate_with_compliance_status_and_authorative_owner(
    asset_service: AssetService,
    repositories: List[AssetView],
):
    for repository in repositories:
        repository.__setattr__("compliance_status", get_compliance_status(repository))

        authorative_owner = [
            owner
            for owner in repository.owner_names
            if asset_service.is_owner_authoritative_for_repository(repository, owner)
        ]
        repository.__setattr__(
            "authorative_owner",
            authorative_owner[0] if len(authorative_owner) > 0 else None,
        )

    return repositories


@repository_standards_main.route("/", methods=["GET"])
@requires_auth
def index():
    asset_service = get_asset_service()
    repositories_raw = asset_service.get_all_repositories()

    repositories = decorate_with_compliance_status_and_authorative_owner(
        asset_service, repositories_raw
    )

    return render_template(
        "projects/repository_standards/pages/home.html",
        repositories=repositories,
        non_compliant_repositories=[
            repo
            for repo in repositories
            if repo.__getattribute__("compliance_status") == "fail"
        ],
    )
