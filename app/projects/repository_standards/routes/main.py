import logging
from collections import defaultdict

from flask import Blueprint, redirect, render_template, request, url_for

from app.projects.repository_standards.repositories.owner_repository import (
    get_owner_repository,
)
from app.projects.repository_standards.services.relationships_service import (
    get_relationships_service,
)
from app.projects.repository_standards.services.repository_compliance_service import (
    get_repository_compliance_service,
)

from app.projects.repository_standards.services.owner_service import (
    get_owner_service,
)
from app.shared.middleware.auth import requires_auth

logger = logging.getLogger(__name__)

repository_standards_main = Blueprint("repository_standards_main", __name__)


@repository_standards_main.route("/", methods=["GET"])
@requires_auth
def index():
    return render_template(
        "projects/repository_standards/pages/home.html",
    )


@repository_standards_main.route("/repositories", methods=["GET"])
@requires_auth
def repositories():
    repository_compliance_service = get_repository_compliance_service()

    repositories = repository_compliance_service.get_all_repositories()

    return render_template(
        "projects/repository_standards/pages/repositories.html",
        repositories=repositories,
        baseline_maturity_level_repositories=[
            repo for repo in repositories if repo.maturity_level >= 1
        ],
        standard_maturity_level_repositories=[
            repo for repo in repositories if repo.maturity_level >= 2
        ],
        exemplar_maturity_level_repositories=[
            repo for repo in repositories if repo.maturity_level >= 3
        ],
    )


@repository_standards_main.route("/business-units", methods=["GET"])
@requires_auth
def business_units():
    owner_repository = get_owner_repository()
    business_units = owner_repository.find_all_business_units()

    return render_template(
        "projects/repository_standards/pages/business_units.html",
        business_unit_names=business_units,
    )


@repository_standards_main.route("/business-units/<owner_id>", methods=["GET"])
@requires_auth
def business_units_owner(owner_id: str):
    repository_compliance_service = get_repository_compliance_service()
    owner_service = get_owner_service()

    owner = owner_service.find_by_id(owner_id)
    if owner is None:
        return "Owner not found", 404
    repositories = repository_compliance_service.get_all_repositories()

    filtrated_repositories = [
        repo
        for repo in repositories
        if owner.name in repo.authorative_business_unit_owners
    ]

    return render_template(
        "projects/repository_standards/pages/business_unit.html",
        repositories=filtrated_repositories,
        baseline_maturity_level_repositories=[
            repo for repo in filtrated_repositories if repo.maturity_level >= 1
        ],
        standard_maturity_level_repositories=[
            repo for repo in filtrated_repositories if repo.maturity_level >= 2
        ],
        exemplar_maturity_level_repositories=[
            repo for repo in filtrated_repositories if repo.maturity_level >= 3
        ],
        owner=owner,
    )


@repository_standards_main.route("/teams", methods=["GET"])
@requires_auth
def teams():
    repository_compliance_service = get_repository_compliance_service()
    owner_repository = get_owner_repository()
    teams = owner_repository.find_all_teams()
    repositories = repository_compliance_service.get_all_repositories()

    team_name_to_id = {team.name: team.id for team in teams}

    team_counts = defaultdict(
        lambda: {
            "repo_count": 0,
            "baseline_compliant_count": 0,
            "standard_compliant_count": 0,
            "exemplar_compliant_count": 0,
        }
    )

    for repo in repositories:
        maturity_level = repo.maturity_level
        team_ids_for_repository = {
            team_name_to_id[owner_name]
            for owner_name in repo.authorative_team_owners
            if owner_name in team_name_to_id
        }

        for team_id in team_ids_for_repository:
            team_counts[team_id]["repo_count"] += 1
            if maturity_level >= 1:
                team_counts[team_id]["baseline_compliant_count"] += 1
            if maturity_level >= 2:
                team_counts[team_id]["standard_compliant_count"] += 1
            if maturity_level >= 3:
                team_counts[team_id]["exemplar_compliant_count"] += 1

    team_counts = {team.id: team_counts[team.id] for team in teams}

    return render_template(
        "projects/repository_standards/pages/teams.html",
        teams=teams,
        team_counts=team_counts,
    )


@repository_standards_main.route("/teams/<owner_id>", methods=["GET"])
@requires_auth
def teams_owner(owner_id: str):
    repository_compliance_service = get_repository_compliance_service()
    owner_service = get_owner_service()

    owner = owner_service.find_by_id(owner_id)
    if owner is None:
        return "Owner not found", 404

    repositories = repository_compliance_service.get_all_repositories()

    filtrated_repositories = [
        repo for repo in repositories if owner.name in repo.authorative_team_owners
    ]

    return render_template(
        "projects/repository_standards/pages/team.html",
        repositories=filtrated_repositories,
        baseline_maturity_level_repositories=[
            repo for repo in filtrated_repositories if repo.maturity_level >= 1
        ],
        standard_maturity_level_repositories=[
            repo for repo in filtrated_repositories if repo.maturity_level >= 2
        ],
        exemplar_maturity_level_repositories=[
            repo for repo in filtrated_repositories if repo.maturity_level >= 3
        ],
        owner=owner,
    )


@repository_standards_main.route("/teams/<owner_id>/edit", methods=["GET", "POST"])
@requires_auth
def edit_team(owner_id: str):
    owner_service = get_owner_service()
    relationships_service = get_relationships_service()

    owner = owner_service.find_by_id(owner_id)
    if owner is None:
        return "Owner not found", 404

    team_name = owner.name
    github_teams = owner.config.teams
    if request.method == "POST":
        form_team_name = str(request.form.get("name"))
        form_github_teams = str(request.form.get("teams"))

        github_teams = [
            team.strip() for team in form_github_teams.split(",") if team.strip()
        ]

        if github_teams and form_team_name:
            updated_owner = owner_service.update_by_id(
                owner_id, form_team_name, github_teams
            )
            if updated_owner is None:
                raise ValueError("Failed to update owner")
            relationships_service.update_relationship_for_owner(updated_owner)

        return redirect(
            url_for("repository_standards_main.teams_owner", owner_id=owner.id)
        )

    return render_template(
        "projects/repository_standards/pages/team_edit.html",
        owner=owner,
        team_name=team_name,
        github_teams=github_teams,
    )


@repository_standards_main.route("/teams/<owner_id>/delete", methods=["POST"])
@requires_auth
def delete_team(owner_id: str):
    owner_service = get_owner_service()

    owner = owner_service.find_by_id(owner_id)
    if owner is None:
        return "Owner not found", 404

    deleted = owner_service.delete_by_id(owner_id)
    if not deleted:
        logger.error(f"Failed to delete owner with id [ {owner_id} ]")
        raise ValueError("Failed to delete owner")

    return redirect(url_for("repository_standards_main.teams"))


@repository_standards_main.route("/teams/add-team", methods=["GET", "POST"])
@requires_auth
def add_team():
    owner_service = get_owner_service()
    relationships_service = get_relationships_service()

    team_name = None
    github_teams = None
    if request.method == "POST":
        form_team_name = str(request.form.get("name"))
        form_github_teams = str(request.form.get("teams"))

        existing_owners_with_same_name = owner_service.find_by_name(form_team_name)
        team_name = form_team_name if len(existing_owners_with_same_name) == 0 else None

        github_teams = [
            team.strip() for team in form_github_teams.split(",") if team.strip()
        ]

        if github_teams and team_name:
            team = owner_service.add_team_owner(team_name, github_teams)

            if team is None:
                raise ValueError("Failed to add team")

            relationships_service.update_relationship_for_owner(team)
            return redirect(
                url_for("repository_standards_main.teams_owner", owner_id=team.id)
            )

    return render_template(
        "projects/repository_standards/pages/team_add_new.html",
        data={"team_name": team_name, "github_teams": github_teams},
    )


@repository_standards_main.route("/unowned-repositories", methods=["GET"])
@requires_auth
def unowned_repositories():
    repository_compliance_service = get_repository_compliance_service()

    repositories = repository_compliance_service.get_all_repositories()

    filtrated_repositories = [
        repo
        for repo in repositories
        if not repo.authorative_business_unit_owners
        and not repo.authorative_team_owners
    ]

    return render_template(
        "projects/repository_standards/pages/unowned_repositories.html",
        repositories=filtrated_repositories,
        baseline_maturity_level_repositories=[
            repo for repo in filtrated_repositories if repo.maturity_level >= 1
        ],
        standard_maturity_level_repositories=[
            repo for repo in filtrated_repositories if repo.maturity_level >= 2
        ],
        exemplar_maturity_level_repositories=[
            repo for repo in filtrated_repositories if repo.maturity_level >= 3
        ],
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
