import requests
import concurrent.futures
import os
import time
import json

GITHUB_API_URL = "https://api.github.com/repos/{org}/{repo}/contents/{directory}"
RAW_URL_TEMPLATE = "https://raw.githubusercontent.com/{org}/{repo}/{branch}/{path}"

# File-based cache that all workers can share
CACHE_FILE = "/tmp/github_modernisation_cache.json"
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