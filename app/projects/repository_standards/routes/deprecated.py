import logging

from flask import Blueprint, redirect

from app.projects.repository_standards.services.repository_compliance_service import (
    get_repository_compliance_service,
)

logger = logging.getLogger(__name__)

repository_standards_deprecated = Blueprint("repository_standards_deprecated", __name__)


@repository_standards_deprecated.route(
    "/api/v1/compliant_public_repositories/<repository_name>",
    methods=["GET"],
)
@repository_standards_deprecated.route(
    "/api/v1/compliant_public_repositories/endpoint/<repository_name>",
    methods=["GET"],
)
@repository_standards_deprecated.route(
    "/api/v2/compliant-repository/<repository_name>",
    methods=["GET"],
)
def deprecated_reports_badge_api(repository_name: str):
    repository_compliance_service = get_repository_compliance_service()

    repository = repository_compliance_service.get_repository_by_name(repository_name)

    if repository and repository.compliance_status == "pass":
        return {
            "color": "005ea5",
            "label": "MoJ Compliant",
            "labelColor": "0b0c0c",
            "message": repository.compliance_status.capitalize()
            if repository
            else "Not Found",
            "schemaVersion": 1,
            "style": "for-the-badge",
        }

    return {
        "color": "cc0000",
        "label": "MoJ Compliant",
        "labelColor": "0b0c0c",
        "message": repository.compliance_status.capitalize()
        if repository
        else "Not Found",
        "schemaVersion": 1,
        "style": "for-the-badge",
    }


@repository_standards_deprecated.route(
    "/public-report/<repository_name>",
    methods=["GET"],
)
def deprecated_report_page_url(repository_name: str):
    return redirect(f"/repository-standards/{repository_name}", code=302)


@repository_standards_deprecated.route(
    "/github_repositories",
    methods=["GET"],
)
def deprecated_reports_homepage():
    return {
        "color": "005ea5",
        "label": "MoJ Compliant",
        "labelColor": "231f20",
        "message": "See https://github-community.service.justice.gov.uk/repository-standards/ or #github-community",
        "schemaVersion": 1,
        "style": "for-the-badge",
    }
