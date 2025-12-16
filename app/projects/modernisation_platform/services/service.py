import requests
import concurrent.futures
import os
import time
import json
import re
import logging
from datetime import datetime, timedelta
from app.shared.config.app_config import app_config

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/repos/{org}/{repo}/contents/{directory}"
RAW_URL_TEMPLATE = "https://raw.githubusercontent.com/{org}/{repo}/{branch}/{path}"

# File-based cache that all workers can share
CACHE_FILE = "/tmp/github_modernisation_cache.json"
README_CACHE_FILE = "/tmp/github_modernisation_readme_cache.json"
WORKFLOW_RUNS_CACHE_FILE = "/tmp/github_modernisation_workflow_runs_cache.json"
CACHE_TTL = 900  # 15 minutes

def get_all_json_data(org, repo, branch, directory):
    now = time.time()
    
    # Try to load from file cache
    cache_data = None
    cache_age = float('inf')
    
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
                cache_age = now - cache_data.get('timestamp', 0)
        except (json.JSONDecodeError, IOError):
            pass
    
    if cache_data and cache_age < CACHE_TTL:
        return cache_data['data']
    
    json_files = list_json_files(org, repo, directory)
    args_list = [(org, repo, branch, file_info) for file_info in json_files]

    # Fetch files concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
        json_data_list = list(executor.map(fetch_json_file_with_filename, args_list))
    
    # Save to file cache
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({
                'data': json_data_list,
                'timestamp': now
            }, f)
    except IOError:
        pass
    
    return json_data_list

def list_json_files(org, repo, directory):
    url = GITHUB_API_URL.format(org=org, repo=repo, directory=directory)
    response = requests.get(url)
    response.raise_for_status()
    files = response.json()
    return [f for f in files if f['name'].endswith('.json')]

def fetch_json_file_with_filename(args):
    org, repo, branch, file_info = args
    raw_url = RAW_URL_TEMPLATE.format(org=org, repo=repo, branch=branch, path=file_info['path'])
    
    response = requests.get(raw_url)
    response.raise_for_status()
    json_data = response.json()
    json_data["_filename"] = file_info["name"].replace(".json", "")
    return json_data

def get_readme_incident_info(org, repo, branch, app_names):
    """
    Fetch README files for apps and extract incident response information.
    Returns a dict mapping app_name to incident info.
    """
    now = time.time()
    
    # Try to load from file cache
    cache_data = None
    cache_age = float('inf')
    
    if os.path.exists(README_CACHE_FILE):
        try:
            with open(README_CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
                cache_age = now - cache_data.get('timestamp', 0)
        except (json.JSONDecodeError, IOError):
            pass
    
    if cache_data and cache_age < CACHE_TTL:
        return cache_data['data']
    
    args_list = [(org, repo, branch, app_name) for app_name in app_names]
    
    # Fetch READMEs concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
        results = list(executor.map(fetch_readme_incident_info, args_list))
    
    # Convert to dict
    incident_info = {app_name: info for app_name, info in results if info}
    
    # Save to file cache
    try:
        with open(README_CACHE_FILE, 'w') as f:
            json.dump({
                'data': incident_info,
                'timestamp': now
            }, f)
    except IOError:
        pass
    
    return incident_info

def fetch_readme_incident_info(args):
    """
    Fetch a single README and extract incident response info.
    Returns tuple (app_name, {incident_hours, incident_contact})
    """
    org, repo, branch, app_name = args
    
    # Try common README naming variations
    readme_paths = [
        f"terraform/environments/{app_name}/README.md",
        f"terraform/environments/{app_name}/ReadMe.md",
        f"terraform/environments/{app_name}/readme.md"
    ]
    
    for path in readme_paths:
        try:
            raw_url = RAW_URL_TEMPLATE.format(org=org, repo=repo, branch=branch, path=path)
            response = requests.get(raw_url, timeout=5)
            
            if response.status_code == 200:
                content = response.text
                incident_hours = extract_section(content, "Incident response hours")
                incident_contact = extract_section(content, "Incident contact details")
                
                logger.debug(f"README found for {app_name}: hours={bool(incident_hours)}, contact={bool(incident_contact)}")
                
                return (app_name, {
                    'incident_hours': incident_hours or 'N/A',
                    'incident_contact': incident_contact or 'N/A'
                })
        except Exception as e:
            logger.debug(f"Error fetching README for {app_name}: {e}")
            continue
    
    logger.debug(f"No README found for {app_name}")
    return (app_name, None)

def extract_section(markdown_content, heading):
    """
    Extract content under a specific heading in markdown.
    Returns the content until the next heading or end of file.
    """
    # Pattern to match the heading (case-insensitive, flexible whitespace)
    # Match any level of heading (one or more #) followed by optional **
    pattern = rf'^#+\s*\*?\*?{re.escape(heading)}:?\*?\*?\s*$'
    
    lines = markdown_content.split('\n')
    in_section = False
    section_lines = []
    
    for line in lines:
        if re.match(pattern, line.strip(), re.IGNORECASE):
            in_section = True
            continue
        
        if in_section:
            # Stop at next heading (any level)
            if re.match(r'^#+\s+', line.strip()):
                break
            section_lines.append(line)
    
    # Clean up the content
    content = '\n'.join(section_lines).strip()
    
    # Remove excessive newlines
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    # Remove HTML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    # Clean up again after removing comments
    content = content.strip()
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    return content if content else None

def get_collaborators_data(org, repo, branch):
    """
    Fetch collaborators.json file.
    Returns the collaborators data with line numbers for each user.
    """
    path = "collaborators.json"
    raw_url = RAW_URL_TEMPLATE.format(org=org, repo=repo, branch=branch, path=path)
    
    try:
        response = requests.get(raw_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Also fetch the raw text to find line numbers
        text_response = requests.get(raw_url, timeout=10)
        lines = text_response.text.split('\n')
        
        # Find line number for each username
        users = data.get("users", [])
        for user in users:
            username = user.get("username", "")
            if username:
                # Search for the line containing this username
                for line_num, line in enumerate(lines, 1):
                    if f'"username": "{username}"' in line:
                        user["_line_number"] = line_num
                        break
        
        return data
    except Exception as e:
        logger.error(f"Error fetching collaborators data: {e}")
        return {"users": []}

def get_failed_workflow_runs(org, repo, branch="main", hours=24):
    """
    Fetch failed GitHub Actions workflow runs for a repository.
    Returns a list of failed workflow runs from the last N hours.
    """
    now = time.time()
    
    # Create a cache key that includes the hours parameter
    cache_file = f"/tmp/github_modernisation_workflow_runs_cache_{hours}h.json"
    
    # Try to load from file cache (shorter TTL for workflow runs)
    cache_data = None
    cache_age = float('inf')
    cache_ttl = 300  # 5 minutes cache for workflow runs
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                cache_age = now - cache_data.get('timestamp', 0)
        except (json.JSONDecodeError, IOError):
            pass
    
    if cache_data and cache_age < cache_ttl:
        return cache_data['data']
    
    # Calculate the cutoff time (last N hours)
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    # Get GitHub token from config (optional for public repos)
    token = app_config.github.token
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    
    url = f"https://api.github.com/repos/{org}/{repo}/actions/runs"
    params = {
        'branch': branch,
        'status': 'failure',
        'per_page': 100
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        # Handle 401 - try without auth for public repos
        if response.status_code == 401 and token:
            logger.warning("GitHub token authentication failed, trying without authentication for public repo")
            headers = {
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28'
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
        
        response.raise_for_status()
        data = response.json()
        
        workflow_runs = []
        for run in data.get('workflow_runs', []):
            # Parse the created_at timestamp and filter by our cutoff time
            created_at_str = run.get('created_at', '')
            try:
                created_at = datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M:%SZ')
                
                # Only include runs within our time window
                if created_at >= cutoff_time:
                    workflow_runs.append({
                        'id': run.get('id'),
                        'name': run.get('name'),
                        'display_title': run.get('display_title'),
                        'status': run.get('status'),
                        'conclusion': run.get('conclusion'),
                        'html_url': run.get('html_url'),
                        'created_at': run.get('created_at'),
                        'updated_at': run.get('updated_at'),
                        'run_number': run.get('run_number'),
                        'event': run.get('event'),
                        'actor': run.get('actor', {}).get('login', 'N/A'),
                        'head_branch': run.get('head_branch'),
                        'head_commit': {
                            'message': run.get('head_commit', {}).get('message', 'N/A'),
                            'author': run.get('head_commit', {}).get('author', {}).get('name', 'N/A')
                        }
                    })
            except (ValueError, TypeError):
                # If we can't parse the date, skip this run
                logger.warning(f"Could not parse created_at for run {run.get('id')}: {created_at_str}")
                continue
        
        # Save to file cache
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'data': workflow_runs,
                    'timestamp': now
                }, f)
        except IOError:
            pass
        
        return workflow_runs
    
    except Exception as e:
        logger.error(f"Error fetching workflow runs: {e}")
        return []

def get_all_workflow_runs(org, repo, branch="main", hours=24):
    """
    Fetch ALL GitHub Actions workflow runs for a repository (all statuses).
    Returns a list of workflow runs from the last N hours.
    """
    now = time.time()
    
    # Create a cache key that includes the hours parameter
    cache_file = f"/tmp/github_modernisation_all_workflow_runs_cache_{hours}h.json"
    
    # Try to load from file cache
    cache_data = None
    cache_age = float('inf')
    cache_ttl = 300  # 5 minutes cache for workflow runs
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                cache_age = now - cache_data.get('timestamp', 0)
        except (json.JSONDecodeError, IOError):
            pass
    
    if cache_data and cache_age < cache_ttl:
        return cache_data['data']
    
    # Calculate the cutoff time (last N hours)
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    # Get GitHub token from config (optional for public repos)
    token = app_config.github.token
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    
    url = f"https://api.github.com/repos/{org}/{repo}/actions/runs"
    
    # Determine how many pages to fetch based on time range
    # More hours = more pages needed
    max_pages = 1
    if hours >= 24 * 7:  # 7 days or more
        max_pages = 5  # Up to 500 runs
    elif hours >= 24 * 2:  # 2 days or more
        max_pages = 3  # Up to 300 runs
    else:
        max_pages = 2  # Up to 200 runs
    
    workflow_runs = []
    page = 1
    should_continue = True
    
    try:
        while should_continue and page <= max_pages:
            params = {
                'branch': branch,
                'per_page': 100,
                'page': page
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            # Handle 401 - try without auth for public repos
            if response.status_code == 401 and token:
                logger.warning("GitHub token authentication failed, trying without authentication for public repo")
                headers = {
                    'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28'
                }
                response = requests.get(url, headers=headers, params=params, timeout=10)
            
            response.raise_for_status()
            data = response.json()
            
            runs_in_page = data.get('workflow_runs', [])
            
            # If no more runs, stop pagination
            if not runs_in_page:
                break
            
            runs_added_this_page = 0
            for run in runs_in_page:
                # Parse the created_at timestamp and filter by our cutoff time
                created_at_str = run.get('created_at', '')
                try:
                    created_at = datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M:%SZ')
                    
                    # If we've gone past our time window, stop fetching more pages
                    if created_at < cutoff_time:
                        should_continue = False
                        break
                    
                    # Include runs within our time window
                    workflow_runs.append({
                        'id': run.get('id'),
                        'name': run.get('name'),
                        'display_title': run.get('display_title'),
                        'status': run.get('status'),
                        'conclusion': run.get('conclusion'),
                        'html_url': run.get('html_url'),
                        'created_at': run.get('created_at'),
                        'updated_at': run.get('updated_at'),
                        'run_number': run.get('run_number'),
                        'event': run.get('event'),
                        'actor': run.get('actor', {}).get('login', 'N/A'),
                        'head_branch': run.get('head_branch'),
                        'head_commit': {
                            'message': run.get('head_commit', {}).get('message', 'N/A'),
                            'author': run.get('head_commit', {}).get('author', {}).get('name', 'N/A')
                        }
                    })
                    runs_added_this_page += 1
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse created_at for run {run.get('id')}: {created_at_str}")
                    continue
            
            # If we didn't add any runs from this page, stop
            if runs_added_this_page == 0:
                break
            
            page += 1
            
        logger.info(f"Fetched {len(workflow_runs)} workflow runs across {page} page(s) for {hours}h time range")
        
        # Save to file cache
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'data': workflow_runs,
                    'timestamp': now
                }, f)
        except IOError:
            pass
        
        return workflow_runs
    
    except Exception as e:
        logger.error(f"Error fetching all workflow runs: {e}")
        return []
    
    