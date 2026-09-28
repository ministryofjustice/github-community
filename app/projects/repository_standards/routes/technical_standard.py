from flask import Blueprint, abort, render_template

from app.projects.repository_standards.services.technical_standard_service import (
    get_technical_standard_service,
)
from app.shared.middleware.auth import requires_auth

technical_standard = Blueprint("technical_standard", __name__)

TEMPLATES = "projects/repository_standards/technical_standard"


@technical_standard.route("/", methods=["GET"])
def index():
    return render_template(f"{TEMPLATES}/home.html")


@technical_standard.route("/repositories", methods=["GET"])
@requires_auth
def repositories():
    repositories = get_technical_standard_service().get_all_repositories()
    return render_template(
        f"{TEMPLATES}/repositories.html",
        repositories=repositories,
        compliant_repositories=[repo for repo in repositories if repo.compliant],
    )


@technical_standard.route("/repositories/<repository_name>", methods=["GET"])
@requires_auth
def repository(repository_name: str):
    repository = get_technical_standard_service().get_repository_by_name(
        repository_name
    )
    if repository is None:
        abort(404)
    return render_template(f"{TEMPLATES}/repository.html", repository=repository)

@technical_standard.route("/contact-us", methods=["GET"])
def contact_us():
    return render_template(f"{TEMPLATES}/contact_us.html")