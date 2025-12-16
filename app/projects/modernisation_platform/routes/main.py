import logging
from flask import Blueprint, render_template, jsonify
from app.projects.modernisation_platform.services.service import get_all_json_data, get_readme_incident_info, get_collaborators_data, get_failed_workflow_runs, get_all_workflow_runs
from datetime import datetime, timedelta
from collections import defaultdict

from app.shared.middleware.auth import requires_auth

logger = logging.getLogger(__name__)

modernisation_platform_main = Blueprint("modernisation_platform_main", __name__)

@modernisation_platform_main.route("/", methods=["GET", "POST"])
@requires_auth
def index():
    return render_template("projects/modernisation_platform/pages/home.html")

@modernisation_platform_main.route("/sandbox-summary")
@requires_auth
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
@requires_auth
def platform_access_summary():
    org = "ministryofjustice"
    repo = "modernisation-platform"
    branch = "main"
    directory = "environments"
    data = get_all_json_data(org, repo, branch, directory)
    
    # Track role counts and collect access items grouped by app
    role_counts = {}
    app_access_map = {}  # Map of app_name -> dict of (env, access_level) -> list of groups
    seen_role_counts = set()  # Track unique (app, env, role) for counting
    
    for app in data:
        app_name = app["_filename"]
        if app_name not in app_access_map:
            app_access_map[app_name] = {}
        
        for env in app.get("environments", []):
            for access in env.get("access", []):
                access_level = access.get("level", "")
                sso_group = access.get("sso_group_name", "")
                
                # Count unique roles per app/env combination (not per team)
                if access_level:
                    count_key = (app_name, env["name"], access_level)
                    if count_key not in seen_role_counts:
                        seen_role_counts.add(count_key)
                        role_counts[access_level] = role_counts.get(access_level, 0) + 1
                
                # Group access details by environment and access level
                if access_level and sso_group:
                    key = (env["name"], access_level)
                    if key not in app_access_map[app_name]:
                        app_access_map[app_name][key] = []
                    
                    # Generate link - Azure groups go to Azure portal, others to GitHub
                    if "azure" in sso_group.lower():
                        group_url = "https://portal.azure.com/#view/Microsoft_AAD_IAM/GroupsManagementMenuBlade/~/AllGroups"
                    else:
                        group_url = f"https://github.com/orgs/ministryofjustice/teams/{sso_group}"
                    
                    app_access_map[app_name][key].append({
                        "group_name": sso_group,
                        "group_url": group_url
                    })
    
    # Define environment order for sorting
    def env_sort_key(item):
        env_name = item[0][0].lower()  # First element of tuple (environment, access_level)
        order = {"development": 0, "dev": 0, "test": 1, "preproduction": 2, "pre-production": 2, "preprod": 2, "production": 3}
        return (order.get(env_name, 999), env_name)  # Unknown environments go last, then alphabetically
    
    # Convert map to list of apps with their access details
    access_items = []
    for app_name in sorted(app_access_map.keys()):
        if app_access_map[app_name]:  # Only include apps with access
            access_details = []
            for (environment, access_level), groups in sorted(app_access_map[app_name].items(), key=env_sort_key):
                access_details.append({
                    "environment": environment,
                    "access_level": access_level,
                    "groups": groups
                })
            
            access_items.append({
                "app_name": app_name,
                "access_details": access_details
            })
    
    # Sort role counts by count (descending) for better display
    role_counts = dict(sorted(role_counts.items(), key=lambda x: x[1], reverse=True))
    
    return render_template(
        "projects/modernisation_platform/pages/platform_access_summary.html",
        role_counts=role_counts,
        access_items=access_items
    )

@modernisation_platform_main.route("/platform-contact-details")
@requires_auth
def platform_contact_details():
    org = "ministryofjustice"
    repo = "modernisation-platform"
    branch = "main"
    directory = "environments"
    data = get_all_json_data(org, repo, branch, directory)
    
    apps = []
    app_names = []
    
    for app in data:
        app_name = app["_filename"]
        app_names.append(app_name)
        
        # Get tags
        tags = app.get("tags", {})
        business_unit = tags.get("business-unit", "N/A")
        contact_email = tags.get("infrastructure-support", "N/A")
        slack_channel = tags.get("slack-channel", "N/A")
        
        apps.append({
            "app_name": app_name,
            "business_unit": business_unit,
            "contact_email": contact_email,
            "slack_channel": slack_channel
        })
    
    # Fetch incident info from READMEs
    readme_org = "ministryofjustice"
    readme_repo = "modernisation-platform-environments"
    readme_branch = "main"
    incident_info = get_readme_incident_info(readme_org, readme_repo, readme_branch, app_names)
    
    # Add incident info to apps
    for app in apps:
        app_name = app["app_name"]
        if app_name in incident_info:
            app["incident_hours"] = incident_info[app_name].get("incident_hours", "N/A")
            app["incident_contact"] = incident_info[app_name].get("incident_contact", "N/A")
        else:
            app["incident_hours"] = "N/A"
            app["incident_contact"] = "N/A"
    
    return render_template(
        "projects/modernisation_platform/pages/platform_contact_details.html",
        apps=apps
    )

@modernisation_platform_main.route("/collaborators-summary")
@requires_auth
def collaborators_summary():
    org = "ministryofjustice"
    repo = "modernisation-platform"
    branch = "main"
    
    data = get_collaborators_data(org, repo, branch)
    users = data.get("users", [])
    
    # Process collaborators data
    collaborators = []
    env_counts = {}
    
    for user in users:
        username = user.get("username", "")
        github_username = user.get("github-username", "N/A")
        accounts = user.get("accounts", [])
        line_number = user.get("_line_number", 1)
        
        # Get environment-role pairs
        env_role_pairs = []
        for account in accounts:
            account_name = account.get("account-name", "")
            access = account.get("access", "")
            
            if account_name:
                env_role_pairs.append({
                    "environment": account_name,
                    "role": access if access else "N/A"
                })
                
                # Count environments
                env_counts[account_name] = env_counts.get(account_name, 0) + 1
        
        # Generate GitHub link to the exact line
        github_file_url = f"https://github.com/{org}/{repo}/blob/{branch}/collaborators.json#L{line_number}"
        
        collaborators.append({
            "username": username,
            "github_username": github_username,
            "env_role_pairs": env_role_pairs,
            "json_link": github_file_url
        })
    
    # Sort environment counts for pie chart
    env_counts_sorted = dict(sorted(env_counts.items(), key=lambda x: x[1], reverse=True)[:10])  # Top 10
    
    return render_template(
        "projects/modernisation_platform/pages/collaborators_summary.html",
        collaborators=collaborators,
        total_collaborators=len(collaborators),
        env_counts=env_counts_sorted
    )

@modernisation_platform_main.route("/workflow-failures")
@requires_auth
def workflow_failures():
    from flask import request
    
    org = "ministryofjustice"
    repo = "modernisation-platform"
    branch = "main"
    
    # Get time range from query parameter, default to 24 hours
    time_range = request.args.get('time_range', '24h')
    
    # Convert time range to hours
    time_range_map = {
        '24h': (24, 'Last 24 hours'),
        '48h': (48, 'Last 48 hours'),
        '7d': (7 * 24, 'Last 7 days'),
        '14d': (14 * 24, 'Last 14 days'),
        '30d': (30 * 24, 'Last 30 days')
    }
    
    hours, time_range_label = time_range_map.get(time_range, (24, 'Last 24 hours'))
    
    # Get all workflow runs for charts and metrics
    all_runs = get_all_workflow_runs(org, repo, branch, hours)
    
    # Filter failed runs
    failed_runs = [run for run in all_runs if run.get('conclusion') == 'failure']
    
    # Calculate metrics
    total_runs = len(all_runs)
    total_failures = len(failed_runs)
    total_success = len([r for r in all_runs if r.get('conclusion') == 'success'])
    success_rate = round((total_success / total_runs * 100) if total_runs > 0 else 0, 1)
    
    # Group failures by workflow name
    workflow_groups = {}
    for run in failed_runs:
        workflow_name = run['name']
        if workflow_name not in workflow_groups:
            workflow_groups[workflow_name] = []
        workflow_groups[workflow_name].append(run)
    
    # Sort each group by created_at (most recent first)
    for workflow_name in workflow_groups:
        workflow_groups[workflow_name].sort(
            key=lambda x: x['created_at'], 
            reverse=True
        )
    
    # Prepare data for timeline chart (group by day)
    timeline_data = defaultdict(lambda: {'success': 0, 'failure': 0, 'cancelled': 0, 'other': 0})
    for run in all_runs:
        # Extract date from created_at
        date_str = run.get('created_at', '')[:10]  # Get YYYY-MM-DD
        conclusion = run.get('conclusion', 'other')
        
        if conclusion == 'success':
            timeline_data[date_str]['success'] += 1
        elif conclusion == 'failure':
            timeline_data[date_str]['failure'] += 1
        elif conclusion == 'cancelled':
            timeline_data[date_str]['cancelled'] += 1
        else:
            timeline_data[date_str]['other'] += 1
    
    # Sort timeline data by date
    sorted_timeline = sorted(timeline_data.items())
    timeline_labels = [date for date, _ in sorted_timeline]
    timeline_success = [data['success'] for _, data in sorted_timeline]
    timeline_failure = [data['failure'] for _, data in sorted_timeline]
    timeline_cancelled = [data['cancelled'] for _, data in sorted_timeline]
    timeline_other = [data['other'] for _, data in sorted_timeline]
    
    # Prepare data for workflow breakdown chart
    workflow_stats = defaultdict(lambda: {'total': 0, 'failures': 0})
    for run in all_runs:
        workflow_name = run['name']
        workflow_stats[workflow_name]['total'] += 1
        if run.get('conclusion') == 'failure':
            workflow_stats[workflow_name]['failures'] += 1
    
    # Calculate failure rates and sort
    workflow_failure_rates = []
    for workflow_name, stats in workflow_stats.items():
        failure_rate = (stats['failures'] / stats['total'] * 100) if stats['total'] > 0 else 0
        workflow_failure_rates.append({
            'name': workflow_name,
            'failure_rate': round(failure_rate, 1),
            'failures': stats['failures'],
            'total': stats['total']
        })
    
    workflow_failure_rates.sort(key=lambda x: x['failure_rate'], reverse=True)
    
    # Calculate MTTR (Mean Time To Recovery)
    # Find pairs of failures followed by successes for the same workflow
    mttr_values = []
    workflow_runs_by_name = defaultdict(list)
    
    for run in all_runs:
        workflow_runs_by_name[run['name']].append(run)
    
    for workflow_name, runs in workflow_runs_by_name.items():
        # Sort by created_at
        sorted_runs = sorted(runs, key=lambda x: x['created_at'])
        
        for i in range(len(sorted_runs) - 1):
            if sorted_runs[i].get('conclusion') == 'failure' and sorted_runs[i + 1].get('conclusion') == 'success':
                try:
                    failure_time = datetime.strptime(sorted_runs[i]['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                    success_time = datetime.strptime(sorted_runs[i + 1]['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                    recovery_time = (success_time - failure_time).total_seconds() / 60  # in minutes
                    mttr_values.append(recovery_time)
                except (ValueError, KeyError):
                    continue
    
    avg_mttr = round(sum(mttr_values) / len(mttr_values)) if mttr_values else 0
    mttr_hours = avg_mttr // 60
    mttr_minutes = avg_mttr % 60
    
    return render_template(
        "projects/modernisation_platform/pages/workflow_failures.html",
        failed_runs=failed_runs,
        workflow_groups=workflow_groups,
        total_runs=total_runs,
        total_failures=total_failures,
        total_success=total_success,
        success_rate=success_rate,
        hours=hours,
        time_range=time_range,
        time_range_label=time_range_label,
        repo_url=f"https://github.com/{org}/{repo}",
        # Chart data
        timeline_labels=timeline_labels,
        timeline_success=timeline_success,
        timeline_failure=timeline_failure,
        timeline_cancelled=timeline_cancelled,
        timeline_other=timeline_other,
        workflow_failure_rates=workflow_failure_rates,
        avg_mttr_hours=mttr_hours,
        avg_mttr_minutes=mttr_minutes
    )

@modernisation_platform_main.route("/platform-environments-summary")
@requires_auth
def platform_environments_summary():
    org = "ministryofjustice"
    repo = "modernisation-platform"
    branch = "main"
    directory = "environments"
    data = get_all_json_data(org, repo, branch, directory)
    
    # Count environments by type
    env_type_counts = {
        "production": 0,
        "preproduction": 0,
        "test": 0,
        "development": 0
    }
    
    # Count critical national infrastructure
    cni_count = 0
    
    # Count account types
    account_type_counts = {}
    
    # Count business units
    business_unit_counts = {}
    
    # Count total accounts (environments)
    total_accounts = 0
    
    # Collect detailed app information for table - grouped by app
    app_details_map = {}
    
    for app in data:
        app_name = app["_filename"]
        tags = app.get("tags", {})
        business_unit_raw = tags.get("business-unit", "Unknown")
        # Normalize business unit to uppercase to handle case inconsistencies
        business_unit = business_unit_raw.upper() if business_unit_raw != "Unknown" else "Unknown"
        is_cni = tags.get("critical-national-infrastructure", False)
        account_type = app.get("account-type", "Unknown")
        
        # Count CNI apps
        if is_cni:
            cni_count += 1
        
        # Count account types (per app, not per environment)
        if account_type:
            account_type_counts[account_type] = account_type_counts.get(account_type, 0) + 1
        
        # Initialize app details if not exists
        if app_name not in app_details_map:
            app_details_map[app_name] = {
                "app_name": app_name,
                "env_types": [],
                "business_unit": business_unit,
                "account_type": account_type,
                "is_cni": "Yes" if is_cni else "No"
            }
        
        environments = app.get("environments", [])
        for env in environments:
            env_name = env.get("name", "").lower()
            
            # Count total accounts
            total_accounts += 1
            
            # Determine environment type for categorization
            env_type = ""
            if env_name == "production":
                env_type_counts["production"] += 1
                env_type = "Production"
            elif env_name in ["preproduction", "pre-production", "preprod"]:
                env_type_counts["preproduction"] += 1
                env_type = "Pre-Production"
            elif env_name == "test":
                env_type_counts["test"] += 1
                env_type = "Test"
            elif env_name in ["development", "dev"]:
                env_type_counts["development"] += 1
                env_type = "Development"
            else:
                env_type = "Other"
            
            # Add environment type to app's list
            if env_type not in app_details_map[app_name]["env_types"]:
                app_details_map[app_name]["env_types"].append(env_type)
            
            # Count business units (count each environment for each app)
            business_unit_counts[business_unit] = business_unit_counts.get(business_unit, 0) + 1
    
    # Convert map to list for template
    app_details = list(app_details_map.values())
    
    # Sort business units by count
    business_unit_counts = dict(sorted(business_unit_counts.items(), key=lambda x: x[1], reverse=True))
    
    return render_template(
        "projects/modernisation_platform/pages/platform_environments_summary.html",
        env_type_counts=env_type_counts,
        cni_count=cni_count,
        account_type_counts=account_type_counts,
        business_unit_counts=business_unit_counts,
        total_apps=len(data),
        total_accounts=total_accounts,
        app_details=app_details
    )
