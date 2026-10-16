import requests
from flask import Blueprint, Response, request

from app.projects.repository_standards.services.technical_standard_badge import (
    get_technical_standard_badge_shield_url,
)
from app.projects.repository_standards.services.technical_standard_service import (
    get_technical_standard_service,
)

repository_standards_api = Blueprint("repository_standards_api", __name__)


@repository_standards_api.route("/<repository_name>/badge", methods=["GET"])
def get_repository_badge(repository_name: str):
    default_badge_style = "for-the-badge"
    valid_badge_styles = ["for-the-badge", "flat"]
    style_parameter = request.args.get("style", default_badge_style, type=str)
    style = (
        style_parameter
        if style_parameter in valid_badge_styles
        else default_badge_style
    )
    repository = get_technical_standard_service().get_repository_by_name(
        repository_name
    )
    shields_url = get_technical_standard_badge_shield_url(
        repository.compliant if repository else None,
        style,
    )
    shields_response = requests.get(shields_url, stream=True)
    return Response(
        shields_response.content, content_type=shields_response.headers["content-type"]
    )
