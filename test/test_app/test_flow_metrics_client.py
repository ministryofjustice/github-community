from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest
import requests
from jwt import PyJWTError

from app.projects.flow_metrics.collector import CollectionError, ProjectClient
from app.shared.services.github_app_client import GitHubAppClient

MODULE = "app.projects.flow_metrics.collector"
SHARED = "app.shared.services.github_app_client"


@pytest.fixture
def config(monkeypatch):
    settings = SimpleNamespace(
        github=SimpleNamespace(app=SimpleNamespace(
            client_id="test-app", private_key="test-key", installation_id=123,
        )),
        auth_enabled=True,
    )
    monkeypatch.setattr(f"{MODULE}.app_config", settings)
    monkeypatch.delenv("FLOW_METRICS_LOCAL_TOKEN", raising=False)
    return settings


@pytest.fixture
def client(config):
    instance = ProjectClient()
    yield instance
    instance.close()


def response(status=200, data=None):
    result = Mock(status_code=status)
    result.json.return_value = {"data": {"node": {"id": "test"}}} if data is None else data
    return result


def test_shared_client_payload_refresh_and_session_lifecycle(client):
    assert isinstance(client.client, GitHubAppClient)
    assert client.session is client.client.session
    assert client.session.adapters["https://"].max_retries.total == 0
    now = datetime.now(UTC)
    replies = [response(), response()]
    with (
        patch(f"{SHARED}.datetime") as clock,
        patch(f"{SHARED}.create_installation_token", side_effect=[
            {"token": "test-first", "expires_at": now + timedelta(minutes=5)},
            {"token": "test-next", "expires_at": now + timedelta(hours=1)},
        ]) as tokens,
        patch.object(client.session, "request", side_effect=replies) as request,
        patch.object(client.session, "close") as close,
    ):
        clock.now.return_value = now
        assert client.query("query($cursor:String){node}", cursor="page-two") == {"node": {"id": "test"}}
        clock.now.return_value = now + timedelta(minutes=6)
        client.query("query{node}")
        assert tokens.call_count == 2
        request.assert_has_calls([
            call("POST", "https://api.github.com/graphql",
                 json={"query": "query($cursor:String){node}", "variables": {"cursor": "page-two"}},
                 timeout=(10, 60), allow_redirects=False),
            call("POST", "https://api.github.com/graphql",
                 json={"query": "query{node}", "variables": {}},
                 timeout=(10, 60), allow_redirects=False),
        ])
        client.close()
        close.assert_called_once()
    for reply in replies:
        reply.close.assert_called_once()


@pytest.mark.parametrize(("status", "attempts"), [(401, 1), (403, 1), (429, 1), (302, 1), (500, 3), (503, 3)])
def test_http_errors_are_safe_and_retries_bounded(client, status, attempts):
    reply = response(status)
    with (
        patch.object(client.client, "get_token", return_value="test"),
        patch.object(client.session, "request", return_value=reply) as request,
        patch(f"{MODULE}.time.sleep") as sleep,
        pytest.raises(CollectionError, match=f"^github_http_{status}$"),
    ):
        client.query("query{node}")
    assert request.call_count == attempts
    assert reply.close.call_count == attempts
    assert sleep.call_args_list == ([call(1), call(2)] if attempts == 3 else [])
    reply.json.assert_not_called()


@pytest.mark.parametrize("failure", [requests.Timeout, requests.ConnectionError])
def test_transport_errors_are_safe_and_retries_bounded(client, failure):
    with (
        patch.object(client.client, "get_token", return_value="test"),
        patch.object(client.session, "request", side_effect=failure("private detail")) as request,
        patch(f"{MODULE}.time.sleep") as sleep,
        pytest.raises(CollectionError, match="^github_connection_failed$"),
    ):
        client.query("query{node}")
    assert request.call_count == 3
    assert sleep.call_args_list == [call(1), call(2)]


def test_transient_failures_can_recover(client):
    failed, good = response(502), response()
    with (
        patch.object(client.client, "get_token", return_value="test"),
        patch.object(client.session, "request", side_effect=[requests.Timeout(), failed, good]),
        patch(f"{MODULE}.time.sleep") as sleep,
    ):
        assert client.query("query{node}") == {"node": {"id": "test"}}
    assert sleep.call_args_list == [call(1), call(2)]
    failed.close.assert_called_once()
    good.close.assert_called_once()


@pytest.mark.parametrize(("data", "code"), [
    ([], "github_invalid_response"),
    ({"data": {}}, "github_query_incomplete"),
    ({"data": None}, "github_query_incomplete"),
    ({"data": ["invalid"]}, "github_query_incomplete"),
    ({"errors": [{"message": "private detail"}], "data": {"node": None}}, "github_query_incomplete"),
])
def test_graphql_partial_and_invalid_results_fail_closed(client, data, code):
    reply = response(data=data)
    with (
        patch.object(client.client, "get_token", return_value="test"),
        patch.object(client.session, "request", return_value=reply) as request,
        pytest.raises(CollectionError, match=f"^{code}$"),
    ):
        client.query("query{node}")
    request.assert_called_once()
    reply.close.assert_called_once()


def test_invalid_json_does_not_expose_response(client):
    reply = response()
    reply.json.side_effect = ValueError("private detail")
    with (
        patch.object(client.client, "get_token", return_value="test"),
        patch.object(client.session, "request", return_value=reply),
        pytest.raises(CollectionError, match="^github_invalid_response$"),
    ):
        client.query("query{node}")
    reply.close.assert_called_once()


@pytest.mark.parametrize("failure", [requests.HTTPError, ValueError, KeyError, PyJWTError])
def test_authentication_errors_are_safe_without_graphql_retry(client, failure):
    with (
        patch(f"{SHARED}.create_installation_token", side_effect=failure("private detail")),
        patch.object(client.session, "request") as request,
        patch(f"{MODULE}.time.sleep") as sleep,
        pytest.raises(CollectionError, match="^github_app_authentication_failed$"),
    ):
        client.query("query{node}")
    request.assert_not_called()
    sleep.assert_not_called()


@pytest.mark.parametrize("auth_enabled", [True, False])
def test_local_fallback_requires_auth_disabled(config, monkeypatch, auth_enabled):
    config.github.app.client_id = None
    config.auth_enabled = auth_enabled
    monkeypatch.setenv("FLOW_METRICS_LOCAL_TOKEN", "test-local-only")
    with patch(f"{MODULE}.GitHubAppClient") as shared:
        if auth_enabled:
            with pytest.raises(CollectionError, match="^github_credentials_missing$"):
                ProjectClient()
        else:
            local = ProjectClient()
            try:
                with patch.object(local.session, "request", return_value=response()) as request:
                    assert local.query("query{node}") == {"node": {"id": "test"}}
                    request.assert_called_once()
                assert local.client is None
            finally:
                local.close()
        shared.assert_not_called()


def test_missing_credentials_never_create_client(config):
    config.github.app.private_key = None
    with pytest.raises(CollectionError, match="^github_credentials_missing$"):
        ProjectClient()


def test_app_credentials_take_precedence_over_local_token(config, monkeypatch):
    config.auth_enabled = False
    monkeypatch.setenv("FLOW_METRICS_LOCAL_TOKEN", "test-local-only")
    client = ProjectClient()
    try:
        assert isinstance(client.client, GitHubAppClient)
        assert "Authorization" not in client.session.headers
    finally:
        client.close()
