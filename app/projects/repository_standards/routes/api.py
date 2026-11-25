import requests
from flask import Blueprint, Response, abort, request

from app.projects.repository_standards.services.technical_standard_badge import (
    get_technical_standard_badge_shield_url,
)
from app.projects.repository_standards.services.technical_standard_service import (
    get_technical_standard_service,
)

repository_standards_api = Blueprint("repository_standards_api", __name__)


@repository_standards_api.route(
    "/<repository_name>/status",
    defaults={"organisation": "ministryofjustice"},
    methods=["GET"],
)
@repository_standards_api.route("/<organisation>/<repository_name>/status", methods=["GET"])
def get_repository_status(repository_name: str, organisation: str):
    repository = get_technical_standard_service().get_repository_by_name(
        repository_name, organisation
    )
    if repository is None or (repository.visibility or "").lower() != "public":
        abort(404)

    rules = {}
    for check in repository.checks:
        anchor = check.link_to_guidance.rsplit("#", 1)[-1]
        rule = anchor.split("-", 1)[-1].replace("must-have-", "has-", 1)
        rule = rule.replace("has-an-", "has-", 1)
        rules[rule.replace("-", "_")] = {
            "pass": "true",
            "fail": "false",
            "not_checked": "not_checked",
        }[check.status]

    return {"compliant": str(repository.compliant).lower(), "rules": rules}


@repository_standards_api.route(
    "/<repository_name>/badge",
    defaults={"organisation": "ministryofjustice"},
    methods=["GET"],
)
@repository_standards_api.route("/<organisation>/<repository_name>/badge", methods=["GET"])
def get_repository_badge(repository_name: str, organisation: str):
    default_badge_style = "for-the-badge"
    valid_badge_styles = ["for-the-badge", "flat"]
    style_parameter = request.args.get("style", default_badge_style, type=str)
    style = (
        style_parameter
        if style_parameter in valid_badge_styles
        else default_badge_style
    )
    repository = get_technical_standard_service().get_repository_by_name(
        repository_name, organisation
    )
    is_public_repository = (
        repository is not None
        and (repository.visibility or "").lower() == "public"
    )
    shields_url = get_technical_standard_badge_shield_url(
        repository.compliant if is_public_repository else None,
        style,
    )
    shields_response = requests.get(shields_url, stream=True)
    return Response(
        shields_response.content, content_type=shields_response.headers["content-type"]
    )
