import logging
import re
from urllib.parse import urlencode

from flask import Blueprint, Response, render_template, request, url_for

from app.projects.repository_stats.config.visibility_config import (
    IMPORT_APPROXIMATE_FROM,
    IMPORT_APPROXIMATE_TO,
    VISIBILITY_ARCHIVED_DEADLINE,
    VISIBILITY_SLACK_CHANNEL_NAME,
    VISIBILITY_SLACK_CHANNEL_URL,
)
from app.projects.repository_stats.repositories.visibility_repository import (
    VisibilityRepository,
)
from app.projects.repository_stats.services.visibility_logic import (
    parse_archived_query,
    parse_visibility_query,
)
from app.projects.repository_stats.services.visibility_ownership import (
    OwnershipRepository,
)
from app.projects.repository_stats.services.visibility_service import (
    VisibilityService,
)
from app.shared.middleware.auth import requires_auth, requires_stats_access

logger = logging.getLogger(__name__)

repository_stats_main = Blueprint("repository_stats_main", __name__)


def overview_anchor(key: str) -> str:
    """A safe, readable id for an organisation or business unit row."""
    return "overview-" + (re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-") or "row")


def overview_anchors(keys: list[str]) -> dict[str, str]:
    """Row ids for every key, with a numeric suffix if two keys slug the same."""
    anchors: dict[str, str] = {}
    used: set[str] = set()
    for key in keys:
        anchor = base = overview_anchor(key)
        suffix = 2
        while anchor in used:
            anchor, suffix = f"{base}-{suffix}", suffix + 1
        used.add(anchor)
        anchors[key] = anchor
    return anchors


def overview_toggle_href(open_keys: list[str], key: str, anchor: str) -> str:
    """Link that opens or closes one organisation ("<org>") or business unit
    ("<org>/<business unit>") and keeps the rest. Closing a row also closes the rows
    inside it."""
    if key in open_keys:
        keys = [k for k in open_keys if k != key and not k.startswith(f"{key}/")]
    else:
        keys = [*open_keys, key]
    query = "?" + urlencode([("open", k) for k in keys]) if keys else ""
    return f"{url_for('repository_stats_main.repository_overview')}{query}#{anchor}"


def get_visibility_service() -> VisibilityService:
    return VisibilityService(
        VisibilityRepository(),
        OwnershipRepository(),
        archived_deadline=VISIBILITY_ARCHIVED_DEADLINE,
    )


@repository_stats_main.route("/", methods=["GET"])
@requires_auth
@requires_stats_access
def index():
    return render_template("projects/repository_stats/pages/home.html")


@repository_stats_main.route("/overview", methods=["GET"])
@requires_auth
@requires_stats_access
def repository_overview():
    page = get_visibility_service().get_overview_page()
    keys = [
        row.key
        for org in page.overview.organisations
        for row in (org, *org.children)
        if row.key
    ]
    open_keys = [
        key for key in dict.fromkeys(request.args.getlist("open")) if key in keys
    ]
    # A business unit only shows when its organisation is open too.
    open_keys = [
        key for key in open_keys if "/" not in key or key.split("/", 1)[0] in open_keys
    ]
    anchors = overview_anchors(keys)
    return render_template(
        "projects/repository_stats/pages/repository_overview.html",
        page=page,
        open_keys=open_keys,
        toggle_hrefs={
            key: overview_toggle_href(open_keys, key, anchors[key]) for key in keys
        },
        anchors=anchors,
    )


@repository_stats_main.route("/visibility", methods=["GET"])
@requires_auth
@requires_stats_access
def visibility_changes():
    page = get_visibility_service().get_changes_page(
        parse_visibility_query(request.args.to_dict())
    )
    return render_template(
        "projects/repository_stats/pages/visibility_changes.html",
        page=page,
        query=page.query,
        import_approximate_from=IMPORT_APPROXIMATE_FROM,
        import_approximate_to=IMPORT_APPROXIMATE_TO,
    )


@repository_stats_main.route("/visibility/changes.csv", methods=["GET"])
@requires_auth
@requires_stats_access
def visibility_changes_csv():
    result = get_visibility_service().get_activity_csv(
        parse_visibility_query(request.args.to_dict())
    )
    if result is None:
        return "Enter a valid date range", 400

    filename, content = result
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@repository_stats_main.route("/archived", methods=["GET"])
@requires_auth
@requires_stats_access
def archived_repositories():
    page = get_visibility_service().get_archived_page(
        parse_archived_query(
            request.args.to_dict(), request.args.getlist("only_public")
        )
    )
    return render_template(
        "projects/repository_stats/pages/archived_repositories.html",
        page=page,
        query=page.query,
        slack_channel_name=VISIBILITY_SLACK_CHANNEL_NAME,
        slack_channel_url=VISIBILITY_SLACK_CHANNEL_URL,
    )
