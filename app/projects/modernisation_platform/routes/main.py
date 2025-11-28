import logging
from flask import Blueprint, render_template, jsonify
from app.projects.modernisation_platform.services.service import get_all_json_data

from app.shared.middleware.auth import requires_auth

logger = logging.getLogger(__name__)

modernisation_platform_main = Blueprint("modernisation_platform_main", __name__)

@modernisation_platform_main.route("/", methods=["GET", "POST"])
@requires_auth
def index():
    return render_template("projects/modernisation_platform/pages/home.html")

@modernisation_platform_main.route("/api/apps-with-sandbox")
def apps_with_sandbox():
    org = "ministryofjustice"
    repo = "modernisation-platform"
    branch = "main"
    directory = "environments"
    data = get_all_json_data(org, repo, branch, directory)
    result = []
    seen = set()
    for app in data:
        for env in app.get("environments", []):
            sandbox_groups = [
                access.get("sso_group_name", "")
                for access in env.get("access", [])
                if access.get("level") == "sandbox"
            ]
            if sandbox_groups:
                key = (app["_filename"], env["name"])
                if key not in seen:
                    seen.add(key)
                    nuke_status = env.get("nuke", "")
                    if env["name"].lower() == "test":
                        nuke_status = "exclude"
                    elif nuke_status not in ["exclude", "rebuild"]:
                        nuke_status = "include"
                    result.append({
                        "app_name": app["_filename"],
                        "environment": env["name"],
                        "nuke": nuke_status,
                        "groups": sandbox_groups
                    })
    return jsonify(result)

@modernisation_platform_main.route("/sandbox-summary")
def sandbox_summary():
    org = "ministryofjustice"
    repo = "modernisation-platform"
    branch = "main"
    directory = "environments"
    data = get_all_json_data(org, repo, branch, directory)
    result = []
    seen = set()
    for app in data:
        for env in app.get("environments", []):
            sandbox_groups = [
                access.get("sso_group_name", "")
                for access in env.get("access", [])
                if access.get("level") == "sandbox"
            ]
            if sandbox_groups:
                key = (app["_filename"], env["name"])
                if key not in seen:
                    seen.add(key)
                    nuke_status = env.get("nuke", "")
                    if env["name"].lower() == "test":
                        nuke_status = "exclude"
                    elif nuke_status not in ["exclude", "rebuild"]:
                        nuke_status = "include"
                    result.append({
                        "app_name": app["_filename"],
                        "environment": env["name"],
                        "nuke": nuke_status,
                        "groups": sandbox_groups
                    })
    return render_template("projects/modernisation_platform/pages/sandbox_summary.html", apps=result)

@modernisation_platform_main.route("/platform-access-summary")
def platform_access_summary():
    org = "ministryofjustice"
    repo = "modernisation-platform"
    branch = "main"
    directory = "environments"
    data = get_all_json_data(org, repo, branch, directory)
    
    # Track role counts and collect all access items
    role_counts = {}
    access_items = []
    seen = set()
    
    for app in data:
        for env in app.get("environments", []):
            for access in env.get("access", []):
                access_level = access.get("level", "")
                sso_group = access.get("sso_group_name", "")
                
                # Count roles
                if access_level:
                    role_counts[access_level] = role_counts.get(access_level, 0) + 1
                
                # Collect unique access items
                key = (app["_filename"], env["name"], access_level)
                if key not in seen and access_level:
                    seen.add(key)
                    # Get all groups for this app/env/level combination
                    groups = [
                        a.get("sso_group_name", "")
                        for a in env.get("access", [])
                        if a.get("level") == access_level and a.get("sso_group_name", "")
                    ]
                    if groups:
                        access_items.append({
                            "app_name": app["_filename"],
                            "environment": env["name"],
                            "access_level": access_level,
                            "groups": groups
                        })
    
    # Sort role counts by count (descending) for better display
    role_counts = dict(sorted(role_counts.items(), key=lambda x: x[1], reverse=True))
    
    return render_template(
        "projects/modernisation_platform/pages/platform_access_summary.html",
        role_counts=role_counts,
        access_items=access_items
    )
