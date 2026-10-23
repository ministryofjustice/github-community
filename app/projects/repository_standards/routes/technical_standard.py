from flask import Blueprint, Response, abort, render_template, request

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
VISIBILITY_FILTERS = {"all", "public", "private", "internal"}


def _filter_repositories_by_visibility(repositories):
    visibility_filter = request.args.get("visibility", "all").lower()
    if visibility_filter not in VISIBILITY_FILTERS:
        abort(400)
    filtered = [
        repository for repository in repositories
        if visibility_filter == "all"
        or (repository.visibility or "").lower() == visibility_filter
    ]
    return filtered, visibility_filter


def _filter_repositories(repositories):
    organisations = sorted({repository.organisation for repository in repositories})
    organisation_filter = request.args.get("organisation", "all").lower()
    filtered, visibility_filter = _filter_repositories_by_visibility(repositories)
    if organisation_filter != "all":
        filtered = [
            repository for repository in filtered
            if repository.organisation.lower() == organisation_filter
        ]
    return filtered, {
        "visibility_filter": visibility_filter,
        "organisation_filter": organisation_filter,
        "organisations": organisations,
    }


def _get_report_filters(service):
    organisations = service.get_organisations()
    organisation_filter = request.args.get("organisation", "all").lower()
    visibility_filter = request.args.get("visibility", "public").lower()
    if visibility_filter not in VISIBILITY_FILTERS:
        abort(400)
    if organisation_filter != "all" and organisation_filter not in organisations:
        abort(400)
    return {
        "organisations": organisations,
        "organisation_filter": organisation_filter,
        "visibility_filter": visibility_filter,
        "organisation": None if organisation_filter == "all" else organisation_filter,
        "visibility": None if visibility_filter == "all" else visibility_filter,
    }


@technical_standard.route("/", methods=["GET"])
def index():
    return render_template(f"{TEMPLATES}/home.html")


@technical_standard.route("/repositories", methods=["GET"])
@requires_auth
def repositories():
    service = get_technical_standard_service()
    filters = _get_report_filters(service)
    repositories = service.get_all_repositories(
        organisation=filters["organisation"], visibility=filters["visibility"]
    )
    return render_template(
        f"{TEMPLATES}/repositories.html",
        repositories=repositories,
        compliant_repositories=[repo for repo in repositories if repo.compliant],
        organisations=filters["organisations"],
        organisation_filter=filters["organisation_filter"],
        visibility_filter=filters["visibility_filter"],
    )


@technical_standard.route("/checks-overview", methods=["GET"])
@requires_auth
def checks_overview():
    service = get_technical_standard_service()
    filters = _get_report_filters(service)
    repositories = service.get_all_repositories(
        organisation=filters["organisation"], visibility=filters["visibility"]
    )
    checks = service.get_check_summaries(repositories)
    return render_template(
        f"{TEMPLATES}/checks_overview.html",
        repositories=repositories,
        checks=checks,
        show_not_checked=any(check["not_checked_count"] for check in checks),
        organisations=filters["organisations"],
        organisation_filter=filters["organisation_filter"],
        visibility_filter=filters["visibility_filter"],
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

    repositories, filters = _filter_repositories(
        get_technical_standard_service().get_repositories_for_owner(owner)
    )
    return render_template(
        f"{TEMPLATES}/repository_list.html",
        title=owner.name,
        parent_title="Business Units",
        parent_url="/repository-standards/technical-standard/business-units",
        repositories=repositories,
        **filters,
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

    repositories, filters = _filter_repositories(
        get_technical_standard_service().get_repositories_for_owner(owner)
    )
    return render_template(
        f"{TEMPLATES}/repository_list.html",
        title=owner.name,
        parent_title="Teams",
        parent_url="/repository-standards/technical-standard/teams",
        repositories=repositories,
        **filters,
    )


@technical_standard.route("/unowned-repositories", methods=["GET"])
@requires_auth
def unowned_repositories():
    service = get_technical_standard_service()
    filters = _get_report_filters(service)
    repositories = service.get_unowned_repositories(
        organisation=filters["organisation"], visibility=filters["visibility"]
    )
    return render_template(
        f"{TEMPLATES}/repository_list.html",
        title="Unowned Repositories",
        parent_title="Technical Standard",
        parent_url="/repository-standards/technical-standard",
        repositories=repositories,
        organisations=filters["organisations"],
        organisation_filter=filters["organisation_filter"],
        visibility_filter=filters["visibility_filter"],
    )


@technical_standard.route(
    "/repositories/<repository_name>",
    defaults={"organisation": "ministryofjustice"},
    methods=["GET"],
)
@technical_standard.route("/repositories/<organisation>/<repository_name>", methods=["GET"])
@requires_auth
def repository(repository_name: str, organisation: str):
    repository = get_technical_standard_service().get_repository_by_name(
        repository_name, organisation
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
