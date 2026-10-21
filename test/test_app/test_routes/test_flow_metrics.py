import time
from unittest.mock import patch

import pytest
from flask import Flask

from app.projects.flow_metrics.config import workspace_config
from app.projects.flow_metrics.routes.main import flow_metrics_main
from app.shared.config.jinja_config import configure_jinja
from app.shared.routes.main import main


@pytest.fixture
def client():
    app = Flask("app")
    app.config.update(TESTING=True, SECRET_KEY="test-only")
    app.register_blueprint(main)
    app.register_blueprint(flow_metrics_main, url_prefix="/flow-metrics/")
    configure_jinja(app)
    return app.test_client()


def test_flow_metrics_requires_hub_auth(client):
    with patch("app.shared.middleware.auth.app_config.auth_enabled", True):
        response = client.get("/flow-metrics/")
    assert response.status_code == 302
    assert response.location == "/auth/login"


def test_flow_metrics_uses_existing_signed_in_session(client):
    with client.session_transaction() as session:
        session["user"] = {"expires_at": time.time() + 3600}
    with patch("app.shared.middleware.auth.app_config.auth_enabled", True):
        response = client.get("/flow-metrics/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Sample data" not in html[:html.index('id="flow-message"')]
    assert html.index('role="tablist"') < html.index('id="data-source"')
    assert 'id="data-source" class="govuk-link"' in html
    assert '<h1 class="govuk-heading-l">Team boards</h1>' in html
    assert html.count('id="data-source"') == 1
    assert html.index('id="collection-status"') > html.index('id="admin-panel"')
    assert html.index('id="live-freshness"') > html.index('id="team-panel"')
    assert "Team boards" in html
    assert "Add team board" in html
    assert "Collector health" not in html
    assert "Example team B" not in html
    assert "Example team C" not in html
    assert "Example team D" not in html
    assert "Current workspace" in html
    assert "No onboarding requests." in html
    assert 'id="admin-save-request"' in html
    assert "Onboarding requests" in html
    assert 'id="admin-setup-form"' in html
    assert 'id="admin-request"' in html
    assert '<dialog id="admin-dialog"' in html
    assert 'aria-labelledby="admin-dialog-title"' in html
    assert 'id="dataset"' not in html
    assert 'id="export-png"' not in html
    assert 'id="export-csv"' in html
    assert "flow-metrics.js" in html
    assert "chart.umd.js" in html
    assert 'id="x-axis"' in html
    assert 'id="y-axis"' in html
    assert 'id="group-by"' in html
    assert 'id="chart-scope"' in html
    assert 'id="filters"' not in html
    assert 'id="toggle-charts"' in html
    assert 'aria-controls="chart-sidebar"' in html
    assert 'id="filter-type"' not in html
    assert 'id="filter-planned"' not in html
    assert 'id="team-hint"' not in html
    assert 'id="builder-hint"' not in html
    assert "<option>DevX</option>" not in html
    assert "All teams" not in html
    assert 'role="combobox"' in html
    assert 'id="filter-suggestions"' in html
    assert 'id="search-save"' in html
    assert "Close items" in html
    assert 'aria-label="Item details"' in html
    assert "Individual items" in html
    assert "Distinct items per sprint" in html
    assert "keyboard-accessible item drill-down" in html
    assert "ticket drill-down" not in html
    assert "Ticket count" not in html
    assert 'value="tickets"' in html  # Existing saved calculation value is unchanged.
    assert 'id="chart-date-ranges"' not in html
    assert 'class="flow-date-ranges"' not in html
    assert 'id="date-range-panel"' in html
    assert 'id="range-from"' in html and 'id="range-to"' in html
    assert html.index('id="date-range-panel"') < html.index('id="search-discard"')
    assert "<strong>Filter by keyword or field &rarr; Date range</strong>" in html
    assert '<h4 class="govuk-heading-s">Date filters</h4>' in html
    assert "Presets end at the latest available date and stay within recorded history." in html
    assert '<a class="govuk-link" href="#guide-save">Save and delete</a>' in html
    assert "updates the shared chart for everyone with workspace access." in html
    assert "Other references are text only." in html
    configuration = html[html.index('<form id="configuration"'):html.index("</form>")]
    for control in ("team", "sprint", "from", "to"):
        assert f'id="{control}"' not in configuration


def test_expired_session_is_not_accepted(client):
    with client.session_transaction() as session:
        session["user"] = {"expires_at": time.time() - 1}
    with patch("app.shared.middleware.auth.app_config.auth_enabled", True):
        assert client.get("/flow-metrics/").status_code == 302


def test_home_links_to_flow_metrics_without_a_demo_only_claim(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'href="/flow-metrics/"' in html
    assert "Explore project board data through shared team charts." in html
    assert "using demonstration data only" not in html


def test_sample_mode_ignores_browser_dataset_switch(client, monkeypatch):
    with client.session_transaction() as session:
        session["user"] = {"expires_at": time.time() + 3600}
    monkeypatch.setenv("FLOW_METRICS_DATA_MODE", "sample")
    monkeypatch.setenv("FLOW_METRICS_ENABLED", "true")
    response = client.get("/flow-metrics/?data=real")
    assert 'data-live="false"' in response.get_data(as_text=True)


def test_workspace_heading_title_and_source_are_configured(client, monkeypatch):
    with client.session_transaction() as session:
        session["user"] = {"expires_at": time.time() + 3600}
    monkeypatch.setenv("FLOW_METRICS_DATA_MODE", "sample")
    monkeypatch.setenv("FLOW_METRICS_WORKSPACE_NAME", "Cloud Platform")
    monkeypatch.setenv(
        "FLOW_METRICS_SOURCE_URL", "https://github.com/orgs/example/projects/42"
    )
    html = client.get("/flow-metrics/").get_data(as_text=True)
    assert '<h1 class="govuk-heading-l"><a id="data-source" class="govuk-link" href="https://github.com/orgs/example/projects/42">Cloud Platform board</a></h1>' in html
    assert "Cloud Platform - Flow Metrics" in html
    assert 'href="https://github.com/orgs/example/projects/42"' in html
    assert "Cloud Platform board</a>" in html


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("FLOW_METRICS_DATA_MODE", "other"),
        ("FLOW_METRICS_WORKSPACE_NAME", " "),
        ("FLOW_METRICS_SOURCE_URL", "javascript:alert(1)"),
    ],
)
def test_invalid_workspace_configuration_fails_explicitly(client, monkeypatch, key, value):
    with client.session_transaction() as session:
        session["user"] = {"expires_at": time.time() + 3600}
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        client.get("/flow-metrics/")


def test_real_mode_requires_enablement_and_matching_source(monkeypatch):
    monkeypatch.setenv("FLOW_METRICS_DATA_MODE", "real")
    monkeypatch.delenv("FLOW_METRICS_ENABLED", raising=False)
    with pytest.raises(ValueError, match="requires FLOW_METRICS_ENABLED"):
        workspace_config()
    monkeypatch.setenv("FLOW_METRICS_ENABLED", "true")
    monkeypatch.setenv("FLOW_METRICS_SOURCE_URL", "https://github.com/orgs/example/projects/42")
    with pytest.raises(ValueError, match="only project 152"):
        workspace_config()
