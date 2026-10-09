import logging
import re
from urllib.parse import urlencode

from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.projects.repository_stats.config.visibility_config import (
    VISIBILITY_ARCHIVED_DEADLINE,
    VISIBILITY_HISTORY_START_DATE,
    VISIBILITY_SLACK_CHANNEL_NAME,
    VISIBILITY_SLACK_CHANNEL_URL,
)
from app.projects.repository_stats.repositories.visibility_repository import (
    VisibilityRepository,
)
from app.projects.repository_stats.services import github_sign_in as github
from app.projects.repository_stats.services.visibility_access import (
    check_stats_access,
    clear_github_sign_in,
    get_github_login,
    remember_github_login,
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
    anchors = overview_anchors(keys)

    open_keys = [
        key for key in dict.fromkeys(request.args.getlist("open")) if key in keys
    ]
    # A business unit only shows when its organisation is open too.
    open_keys = [
        key for key in open_keys if "/" not in key or key.split("/", 1)[0] in open_keys
    ]

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
        history_start_date=VISIBILITY_HISTORY_START_DATE,
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


# GitHub sign-in: confirms which GitHub account the signed-in user has, so their
# membership of the access team can be checked. See services/github_sign_in.py.
# Stats pages redirect straight to /github/login. Failures always show a problem page
# with a "Try again" button rather than redirecting to GitHub again, so there's no loop.

PROBLEM_TEMPLATE = "projects/repository_stats/pages/github_problem.html"


def render_no_access():
    return (
        render_template(
            "projects/repository_stats/pages/no_access.html",
            github_login=get_github_login(session.get("user")),
            slack_channel_name=VISIBILITY_SLACK_CHANNEL_NAME,
            slack_channel_url=VISIBILITY_SLACK_CHANNEL_URL,
        ),
        403,
    )


def render_github_problem(problem: str, status: int, retry_href: str | None = None):
    """problem: "cancelled", "state", "failed", "unavailable" or "not_configured".

    retry_href defaults to starting the GitHub sign-in again.
    """
    return (
        render_template(
            PROBLEM_TEMPLATE,
            problem=problem,
            retry_href=retry_href or url_for("repository_stats_main.github_login"),
            slack_channel_name=VISIBILITY_SLACK_CHANNEL_NAME,
            slack_channel_url=VISIBILITY_SLACK_CHANNEL_URL,
        ),
        status,
    )


def github_callback_url() -> str:
    # Built from the request host so dev and both production hostnames work. Always
    # https, like the Auth0 callback: TLS ends at the ingress in front of the app.
    return url_for(
        "repository_stats_main.github_callback", _external=True, _scheme="https"
    )


@repository_stats_main.route("/github/login", methods=["GET"])
@requires_auth
def github_login():
    # Stats pages send people here with the page to return to. Without a "next" (e.g.
    # "Try again") keep any page already remembered.
    if next_path := github.safe_next_path(request.args.get("next")):
        session[github.NEXT_SESSION_KEY] = next_path
    if not github.is_configured():
        logger.warning("Repository Stats GitHub sign-in is not configured")
        return render_github_problem("not_configured", 503)
    return redirect(github.authorize_url(github_callback_url(), session))


@repository_stats_main.route("/github/callback", methods=["GET"])
@requires_auth
def github_callback():
    state_matches = github.take_state_matches(request.args.get("state"), session)
    if not state_matches:
        logger.warning("Repository Stats GitHub sign-in state was missing or wrong")
        return render_github_problem("state", 400)
    error = request.args.get("error")
    if error == "access_denied":
        return render_github_problem("cancelled", 200)
    code = request.args.get("code")
    if error or not code:
        logger.warning("Repository Stats GitHub sign-in returned no code")
        return render_github_problem("failed", 400)
    if not github.is_configured():
        logger.warning("Repository Stats GitHub sign-in is not configured")
        return render_github_problem("not_configured", 503)

    try:
        login = github.fetch_github_login(code, github_callback_url())
    except github.GitHubUnavailableError as error:
        logger.warning("Repository Stats GitHub sign-in failed: %s", error)
        return render_github_problem("unavailable", 503)
    except github.GitHubSignInError as error:
        logger.warning("Repository Stats GitHub sign-in failed: %s", error)
        return render_github_problem("failed", 502)

    remember_github_login(session.get("user"), login)
    # Check the team now so the result is ready for the page we send them back to.
    check_stats_access(session.get("user"))
    next_path = github.safe_next_path(session.pop(github.NEXT_SESSION_KEY, None))
    return redirect(next_path or url_for("repository_stats_main.index"))


@repository_stats_main.route("/github/switch", methods=["POST"])
@requires_auth
def github_switch_account():
    clear_github_sign_in(session)
    return redirect(url_for("repository_stats_main.github_login"))
