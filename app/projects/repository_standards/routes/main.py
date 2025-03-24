import logging

from flask import Blueprint, render_template
from app.projects.repository_standards.services.repository_compliance_service import (
    get_repository_compliance_service,
)
from app.projects.repository_standards.repositories.owner_repository import (
    get_owner_repository,
)

from app.shared.middleware.auth import requires_auth

logger = logging.getLogger(__name__)

repository_standards_main = Blueprint("repository_standards_main", __name__)


@repository_standards_main.route("/", methods=["GET"])
@requires_auth
def index():
    owner_repository = get_owner_repository()
    owners = owner_repository.find_all_names()

    return render_template(
        "projects/repository_standards/pages/home.html",
        owners=owners,
    )


@repository_standards_main.route("/repositories", methods=["GET"])
@requires_auth
def repositories():
    repository_compliance_service = get_repository_compliance_service()

    repositories = repository_compliance_service.get_all_repositories()

    return render_template(
        "projects/repository_standards/pages/repositories.html",
        repositories=repositories,
        non_compliant_repositories=[
            repo for repo in repositories if repo.compliance_status == "fail"
        ],
    )


@repository_standards_main.route("/business-units", methods=["GET"])
@requires_auth
def business_units():
    owner_repository = get_owner_repository()
    owners = owner_repository.find_all_names()

    return render_template(
        "projects/repository_standards/pages/business_units.html",
        owners=owners,
    )


@repository_standards_main.route("/business-units/<owner>", methods=["GET"])
@requires_auth
def owner(owner: str):
    repository_compliance_service = get_repository_compliance_service()

    repositories = repository_compliance_service.get_all_repositories()

    filtrated_repositories = [
        repo for repo in repositories if owner == repo.authorative_owner
    ]

    return render_template(
        "projects/repository_standards/pages/business_unit.html",
        repositories=filtrated_repositories,
        non_compliant_repositories=[
            repo for repo in filtrated_repositories if repo.compliance_status == "fail"
        ],
        owner=owner,
    )


@repository_standards_main.route("/<repository_name>", methods=["GET"])
@requires_auth
def repository_compliance_report(repository_name: str):
    repository_compliance_service = get_repository_compliance_service()

    repository = repository_compliance_service.get_repository_by_name(repository_name)

    if repository is None:
        return "Repository not found", 404

    return render_template(
        "projects/repository_standards/pages/repository.html",
        repository=repository,
    )


@repository_standards_main.route("/contact-us", methods=["GET"])
def contact_us():
    return render_template("projects/repository_standards/pages/contact_us.html")


@repository_standards_main.route("/guidance", methods=["GET"])
def guidance():
    return render_template("projects/repository_standards/pages/guidance.html")
