import logging

from flask import Blueprint, redirect, url_for

from app.projects.repository_standards.services.technical_standard_service import (
    get_technical_standard_service,
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
    repository = get_technical_standard_service().get_repository_by_name(
        repository_name, "ministryofjustice"
    )
    if repository is None:
        message, color = "NOT FOUND", "b1b4b6"
    elif repository.compliant:
        message, color = "COMPLIANT", "cce2d8"
    else:
        message, color = "NON-COMPLIANT", "f4cdc6"

    return {
        "color": color,
        "label": "MOJ",
        "labelColor": "0b0c0c",
        "message": message,
        "schemaVersion": 1,
        "style": "for-the-badge",
    }


@repository_standards_deprecated.route(
    "/public-report/<repository_name>",
    methods=["GET"],
)
def deprecated_report_page_url(repository_name: str):
    return redirect(
        url_for(
            "technical_standard.repository",
            repository_name=repository_name,
            organisation="ministryofjustice",
        ),
        code=302,
    )


@repository_standards_deprecated.route(
    "/github_repositories",
    methods=["GET"],
)
def deprecated_reports_homepage():
    return {
        "color": "005ea5",
        "label": "MoJ Compliant",
        "labelColor": "231f20",
        "message": "See https://github-community.service.justice.gov.uk/repository-standards/ or #ask-developer-experience",
        "schemaVersion": 1,
        "style": "for-the-badge",
    }
