import logging

from github import Auth, GithubIntegration

logger = logging.getLogger(__name__)


def get_github_app_auth_headers(client_id: str, private_key: str, installation_id: int) -> dict:

    logger.info(f"Authenticating via GitHub App (client_id: {client_id[:10]}..., installation_id: {installation_id})")

    auth = Auth.AppAuth(client_id, private_key)
    gi = GithubIntegration(auth=auth)
    token = gi.get_access_token(int(installation_id)).token

    return {"Authorization": f"token {token}"}
