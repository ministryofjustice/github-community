from flask import Blueprint, Response, abort, render_template

from app.projects.repository_standards.repositories.owner_repository import (
    get_owner_repository,
)
from app.projects.repository_standards.services.owner_service import (
    get_owner_service,
)
from app.projects.repository_standards.services.technical_standard_service import (
    get_technical_standard_service,
)
from app.projects.repository_standards.services.technical_standard_badge import (
    get_technical_standard_badge_svg,
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


@technical_standard.route("/checks-overview", methods=["GET"])
@requires_auth
def checks_overview():
    service = get_technical_standard_service()
    repositories = service.get_all_repositories()
    checks = service.get_check_summaries(repositories)
    return render_template(
        f"{TEMPLATES}/checks_overview.html",
        repositories=repositories,
        checks=checks,
        show_not_checked=any(check["not_checked_count"] for check in checks),
    )


@technical_standard.route("/business-units", methods=["GET"])
@requires_auth
def business_units():
    owners = get_owner_repository().find_all_business_units()
    service = get_technical_standard_service()

    return render_template(
        f"{TEMPLATES}/owner_summaries.html",
        owners=owners,
        owner_counts=service.get_owner_counts(owners),
        owner_type="Business Unit",
        owner_type_plural="Business Units",
        owner_url_prefix="/repository-standards/technical-standard/business-units",
    )


@technical_standard.route("/business-units/<owner_id>", methods=["GET"])
@requires_auth
def business_unit(owner_id: str):
    owner = get_owner_service().find_by_id(owner_id)
    if owner is None or owner.type != "BUSINESS_UNIT":
        abort(404)

    return render_template(
        f"{TEMPLATES}/repository_list.html",
        title=owner.name,
        parent_title="Business Units",
        parent_url="/repository-standards/technical-standard/business-units",
        repositories=get_technical_standard_service().get_repositories_for_owner(owner),
    )


@technical_standard.route("/teams", methods=["GET"])
@requires_auth
def teams():
    owners = get_owner_repository().find_all_teams()
    service = get_technical_standard_service()

    return render_template(
        f"{TEMPLATES}/owner_summaries.html",
        owners=owners,
        owner_counts=service.get_owner_counts(owners),
        owner_type="Team",
        owner_type_plural="Teams",
        owner_url_prefix="/repository-standards/technical-standard/teams",
    )


@technical_standard.route("/teams/<owner_id>", methods=["GET"])
@requires_auth
def team(owner_id: str):
    owner = get_owner_service().find_by_id(owner_id)
    if owner is None or owner.type != "TEAM":
        abort(404)

    return render_template(
        f"{TEMPLATES}/repository_list.html",
        title=owner.name,
        parent_title="Teams",
        parent_url="/repository-standards/technical-standard/teams",
        repositories=get_technical_standard_service().get_repositories_for_owner(owner),
    )


@technical_standard.route("/unowned-repositories", methods=["GET"])
@requires_auth
def unowned_repositories():
    return render_template(
        f"{TEMPLATES}/repository_list.html",
        title="Unowned Repositories",
        parent_title="Technical Standard",
        parent_url="/repository-standards/technical-standard",
        repositories=get_technical_standard_service().get_unowned_repositories(),
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


@technical_standard.route("/badges/<status>.svg", methods=["GET"])
@requires_auth
def report_badge(status: str):
    if status not in {"compliant", "non-compliant"}:
        abort(404)

    response = Response(
        get_technical_standard_badge_svg(status == "compliant"),
        mimetype="image/svg+xml",
    )
    response.headers["Cache-Control"] = "private, max-age=60, must-revalidate"
    return response


@technical_standard.route("/contact-us", methods=["GET"])
def contact_us():
    return render_template(f"{TEMPLATES}/contact_us.html")
