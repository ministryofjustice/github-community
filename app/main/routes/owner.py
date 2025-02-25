import logging

import requests
from flask import Blueprint, abort, render_template, request

from app.main.middleware.auth import requires_auth
from app.main.repositories.asset_repository import AssetView
from app.main.repositories.owner_repository import get_owner_repository
from app.main.services.asset_service import get_asset_service
from app.main.services.circleci_service import (
    get_circleci_service,
)

logger = logging.getLogger(__name__)

owner_route = Blueprint("owner_route", __name__)


def filter_by_compliance_status(
    compliance_status: str,
    repositories: list[AssetView],
    repositories_compliance_map: dict[str, str],
):
    filtered_repositories_by_compliance_status = []
    for repository in repositories:
        if (
            repository.name in repositories_compliance_map
            and repositories_compliance_map[repository.name] == compliance_status
        ):
            filtered_repositories_by_compliance_status += [repository]

    return filtered_repositories_by_compliance_status


def get_repositories_compliance_map(repositories: list[AssetView]):
    repository_names = [repository.name for repository in repositories]
    return requests.post(
        "https://operations-engineering-reports.cloud-platform.service.justice.gov.uk/api/public-compliance-report",
        json={"repository_names": repository_names},
    ).json()


@owner_route.route("/", methods=["GET"])
@requires_auth
def index():
    repository_name = request.args.get("repository-name")
    selected_owner = request.args.get("owner") or "NO_OWNER"
    selected_access_levels = request.args.getlist("access-levels")
    authoritative_owners_only = bool(request.args.get("authorative_owners_only"))

    owner_repository = get_owner_repository()
    asset_service = get_asset_service()

    owners = owner_repository.find_all_names()

    filtered_repositories = []
    if "NO_OWNER" == selected_owner:
        filtered_repositories = [
            repository
            for repository in asset_service.get_all_repositories()
            if not repository.owner_names
        ]
    else:
        for repository in asset_service.get_all_repositories():
            if (
                authoritative_owners_only
                and asset_service.is_owner_authoritative_for_repository(
                    repository, selected_owner
                )
            ):
                filtered_repositories += [repository]
            elif (
                not authoritative_owners_only
                and selected_owner in repository.owner_names
            ):
                filtered_repositories += [repository]

    filtered_repositories_by_name = []
    if repository_name:
        for repository in filtered_repositories:
            if repository_name and repository_name in repository.name:
                filtered_repositories_by_name = filtered_repositories_by_name + [
                    repository
                ]
    else:
        filtered_repositories_by_name = filtered_repositories

    repositories_filtered_by_access_level = filtered_repositories_by_name

    return render_template(
        "pages/owner.html",
        repositories=repositories_filtered_by_access_level,
        repository_name=repository_name if repository_name else "",
        selected_owners=selected_owner,
        owners=owners,
        access_levels=["ADMIN", "OTHER"],
        selected_access_levels=selected_access_levels
        if selected_access_levels
        else ["ADMIN", "OTHER"],
        exclude_other_relationships_where_admins_exist=authoritative_owners_only,
    )


@owner_route.route("/<owner>", methods=["GET"])
@requires_auth
def owner_dashboard(owner: str):
    asset_service = get_asset_service()
    owner_repository = get_owner_repository()
    circleci_service = get_circleci_service()

    owners = owner_repository.find_all_names()
    if owner not in owners:
        abort(404)

    repositories = asset_service.get_repositories_by_authoratative_owner(owner)
    repositories_without_admin_access = asset_service.get_repositories_by_authoratative_owner_filtered_by_missing_admin_access(
        owner
    )
    repositories_compliance_map = get_repositories_compliance_map(repositories)
    non_compliant_repositories = filter_by_compliance_status(
        "FAIL", repositories, repositories_compliance_map
    )

    circleci_projects = circleci_service.get_circleci_project_metrics_for_repositories(
        repositories
    )
    circleci_cost = circleci_service.get_total_cost_of_projects(circleci_projects)

    return render_template(
        "pages/owner_dashboard.html",
        owner=owner,
        repositories=repositories,
        repositories_without_admin_access=repositories_without_admin_access,
        non_compliant_repositories=non_compliant_repositories,
        circle_cost=circleci_cost,
    )


@owner_route.route("/<owner>/all-repositories", methods=["GET"])
@requires_auth
def owner_dashboard_all_repositories(owner: str):
    asset_service = get_asset_service()
    owner_repository = get_owner_repository()

    owners = owner_repository.find_all_names()
    if owner not in owners:
        abort(404)

    repositories = asset_service.get_repositories_by_authoratative_owner(owner)
    repositories_compliance_map = get_repositories_compliance_map(repositories)
    return render_template(
        "pages/owner_dashboard_all_repositories.html",
        owner=owner,
        repositories=repositories,
        repositories_compliance_map=repositories_compliance_map,
    )


@owner_route.route("/<owner>/repositories-without-admin-access", methods=["GET"])
@requires_auth
def owner_dashboard_repositories_without_admin_access(owner: str):
    asset_service = get_asset_service()
    owner_repository = get_owner_repository()

    owners = owner_repository.find_all_names()
    if owner not in owners:
        abort(404)

    repositories = asset_service.get_repositories_by_authoratative_owner_filtered_by_missing_admin_access(
        owner
    )
    return render_template(
        "pages/owner_dashboard_repositories_without_admin_access.html",
        owner=owner,
        repositories=repositories,
    )


@owner_route.route("/<owner>/non-compliant-repositories", methods=["GET"])
@requires_auth
def owner_dashboard_non_compliant_repositories_report(owner: str):
    asset_service = get_asset_service()
    owner_repository = get_owner_repository()

    owners = owner_repository.find_all_names()
    if owner not in owners:
        abort(404)

    owner_repositories = asset_service.get_repositories_by_authoratative_owner(owner)
    repositories_compliance_map = get_repositories_compliance_map(owner_repositories)
    repositories = filter_by_compliance_status(
        "FAIL", owner_repositories, repositories_compliance_map
    )

    return render_template(
        "pages/owner_dashboard_non_compliant_repositories_report.html",
        owner=owner,
        repositories=repositories,
        repositories_compliance_map=repositories_compliance_map,
    )


@owner_route.route("/<owner>/circleci", methods=["GET"])
@requires_auth
def owner_dashboard_circleci(owner: str):
    circleci_service = get_circleci_service()
    asset_service = get_asset_service()
    owner_repository = get_owner_repository()

    owners = owner_repository.find_all_names()
    if owner not in owners:
        abort(404)

    repositories = asset_service.get_repositories_by_authoratative_owner(owner)

    circleci_projects = circleci_service.get_circleci_project_metrics_for_repositories(
        repositories
    )

    return render_template(
        "pages/owner_dashboard_circleci.html",
        owner=owner,
        circleci_projects=circleci_projects,
    )
