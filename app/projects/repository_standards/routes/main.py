import logging

from flask import Blueprint, render_template
from app.projects.repository_standards.services.repository_compliance_service import (
    get_repository_compliance_service,
)


from app.shared.middleware.auth import requires_auth

logger = logging.getLogger(__name__)

repository_standards_main = Blueprint("repository_standards_main", __name__)


@repository_standards_main.route("/", methods=["GET"])
@requires_auth
def index():
    repository_compliance_service = get_repository_compliance_service()

    repositories = repository_compliance_service.get_all_repositories()

    return render_template(
        "projects/repository_standards/pages/home.html",
        repositories=repositories,
        non_compliant_repositories=[
            repo for repo in repositories if repo.compliance_status == "fail"
        ],
    )


@repository_standards_main.route(
    "/<repository_name>/compliance-report", methods=["GET"]
)
@requires_auth
def repository_compliance_report(repository_name: str):
    repository_compliance_service = get_repository_compliance_service()

    repository = repository_compliance_service.get_repository_by_name(repository_name)

    if repository is None:
        return "Repository not found", 404

    return render_template(
        "projects/repository_standards/pages/repository_compliance_report.html",
        repository=repository,
    )
