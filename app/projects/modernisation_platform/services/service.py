import requests

GITHUB_API_URL = "https://api.github.com/repos/{org}/{repo}/contents/{directory}"
RAW_URL_TEMPLATE = "https://raw.githubusercontent.com/{org}/{repo}/{branch}/{path}"

def list_json_files(org, repo, directory):
    url = GITHUB_API_URL.format(org=org, repo=repo, directory=directory)
    print(f"Fetching file list from: {url}")  # Debug
    response = requests.get(url)
    response.raise_for_status()
    files = response.json()
    print(f"Found files: {[f['name'] for f in files]}")  # Debug
    return [f for f in files if f['name'].endswith('.json')]

def fetch_json_file(org, repo, branch, path):
    raw_url = RAW_URL_TEMPLATE.format(org=org, repo=repo, branch=branch, path=path)
    print(f"Fetching JSON from: {raw_url}")  # Debug
    response = requests.get(raw_url)
    response.raise_for_status()
    return response.json()

def get_all_json_data(org, repo, branch, directory):
    json_files = list_json_files(org, repo, directory)
    json_data_list = []
    for file_info in json_files:
        json_data = fetch_json_file(org, repo, branch, file_info['path'])
        json_data["_filename"] = file_info["name"].replace(".json", "")
        json_data_list.append(json_data)
    return json_data_list