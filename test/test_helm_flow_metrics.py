"""Render-only Helm checks; never contact Kubernetes or use real credentials."""

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

CHART = Path("helm/github-community")


@pytest.fixture
def helm():
    executable = os.environ.get("HELM_BINARY") or shutil.which("helm")
    if not executable:
        pytest.skip("Helm is required for chart rendering checks.")
    return executable


def render(helm, environment="dev", settings=(), upgrade=False, release="github-community", namespace=None):
    command = [
        helm, "template", release, str(CHART),
        "-f", str(CHART / f"values-{environment}.yaml"),
        "--set", "app.deployment.image.repository=synthetic/hub",
        "--set", "app.deployment.image.tag=generated-test",
        "--namespace", namespace or f"github-community-{environment}",
    ]
    if upgrade:
        command.append("--is-upgrade")
    for setting in settings:
        command.extend(["--set" if setting.split("=")[0].endswith(".enabled") else "--set-string", setting])
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def sample_jobs(documents):
    return [document for document in documents if document["kind"] == "Job"
            and document["metadata"]["name"].endswith("-flow-metrics-init-sample")]


@pytest.mark.parametrize("upgrade", [False, True])
def test_dev_sample_hook_is_bounded_restricted_and_database_only(helm, upgrade):
    job, = sample_jobs(render(helm, upgrade=upgrade))
    annotations = job["metadata"]["annotations"]
    assert annotations["helm.sh/hook"] == "post-install,post-upgrade"
    assert annotations["helm.sh/hook-delete-policy"] == "before-hook-creation,hook-succeeded"
    assert job["spec"]["backoffLimit"] == 6
    assert job["spec"]["activeDeadlineSeconds"] == 600
    pod = job["spec"]["template"]["spec"]
    assert pod["restartPolicy"] == "Never"
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"] == {
        "runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"},
    }
    container, = pod["containers"]
    assert container["image"] == "synthetic/hub:generated-test"
    assert container["command"] == ["python3", "-m", "flask"]
    assert container["args"] == ["--app", "app.app", "flow-metrics", "init-sample"]
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]},
        "runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"},
    }
    assert {entry["name"] for entry in container["env"]} == {
        "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST", "POSTGRES_PORT",
    }


def test_production_does_not_initialise_samples(helm):
    assert not sample_jobs(render(helm, "prod"))


def test_dev_hook_can_be_disabled(helm):
    documents = render(helm, settings=("app.jobs.flow_metrics_init_sample.enabled=false",))
    assert not sample_jobs(documents)


def test_hook_name_remains_within_kubernetes_limit(helm):
    job, = sample_jobs(render(helm, release="generated-long-release-name-for-flow-metrics-test"))
    assert len(job["metadata"]["name"]) <= 63


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_dev_uses_combined_exploration_with_genuine_collection(helm, environment):
    deployment, = [d for d in render(helm, environment) if d["kind"] == "Deployment"]
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    assert [entry for entry in env if entry["name"].startswith("FLOW_METRICS_")] == (
        [
            {"name": "FLOW_METRICS_ENABLED", "value": "true"},
            {"name": "FLOW_METRICS_DATA_MODE", "value": "sample"},
        ] if environment == "dev" else []
    )
    assert not [entry for entry in env if entry["name"] == "AUTH_ENABLED"]


def test_explicit_flow_environment_is_quoted_and_does_not_enter_job(helm):
    expected = {
        "FLOW_METRICS_ENABLED": "false",
        "FLOW_METRICS_DATA_MODE": "sample",
        "FLOW_METRICS_WORKSPACE_NAME": "Generated workspace",
        "FLOW_METRICS_SOURCE_URL": "https://github.com/orgs/example/projects/42",
    }
    documents = render(helm, settings=("app.jobs.flow_metrics_reconcile.enabled=false",) + tuple(
        f"app.deployment.env.{name}={value}" for name, value in expected.items()
    ))
    deployment, = [d for d in documents if d["kind"] == "Deployment"]
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    actual = {entry["name"]: entry.get("value") for entry in env}
    assert all(actual[name] == value for name, value in expected.items())
    job, = sample_jobs(documents)
    job_env = job["spec"]["template"]["spec"]["containers"][0]["env"]
    assert not [entry for entry in job_env if entry["name"].startswith("FLOW_METRICS_")]


CAPTURE_SETTINGS = (
    "app.jobs.flow_metrics_reconcile.enabled=true",
)


def capture_jobs(documents):
    return [d for d in documents if d["kind"] == "CronJob"
            and "-flow-metrics-" in d["metadata"]["name"]]


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_scheduled_capture_is_enabled_only_in_dev(helm, environment):
    documents = render(helm, environment)
    jobs = capture_jobs(documents)
    assert len(jobs) == (1 if environment == "dev" else 0)
    assert all(job["metadata"]["name"].endswith("-flow-metrics-reconcile") for job in jobs)
    assert not [d for d in documents if d["kind"] == "Secret"]


def test_dev_capture_can_be_disabled_for_rollback(helm):
    documents = render(helm, settings=("app.jobs.flow_metrics_reconcile.enabled=false",))
    assert not capture_jobs(documents)
    deployment, = [d for d in documents if d["kind"] == "Deployment"]
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    assert {entry["name"]: entry["value"] for entry in env if entry["name"].startswith("FLOW_METRICS_")} == {
        "FLOW_METRICS_ENABLED": "true",
        "FLOW_METRICS_DATA_MODE": "sample",
    }


def test_default_schedule_is_five_london_weekday_slots_across_dst(helm):
    job, = capture_jobs(render(helm))
    minute, hours, day, month, weekdays = job["spec"]["schedule"].split()
    assert (minute, day, month, weekdays) == ("30", "*", "*", "1-5")
    assert hours == "9,11,13,15,17"
    zone = ZoneInfo(job["spec"]["timeZone"])
    for date, offset in [((2026, 3, 27), 0), ((2026, 3, 30), 1),
                         ((2026, 10, 23), 1), ((2026, 10, 26), 0)]:
        instants = [datetime(*date, hour, int(minute), tzinfo=zone) for hour in map(int, hours.split(","))]
        assert all(instant.isoweekday() in range(1, 6) for instant in instants)
        assert [instant.astimezone(UTC).hour for instant in instants] == [
            hour - offset for hour in (9, 11, 13, 15, 17)
        ]
    for date in [(2026, 10, 24), (2026, 10, 25)]:
        assert datetime(*date, tzinfo=zone).isoweekday() not in range(1, 6)


def test_receiver_and_processor_have_no_deployment_wiring(helm):
    documents = render(helm, settings=CAPTURE_SETTINGS)
    deployment, = [d for d in documents if d["kind"] == "Deployment"]
    env = {entry["name"]: entry for entry in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["FLOW_METRICS_ENABLED"]["value"] == "true"
    assert not any(name.startswith("FLOW_METRICS_WEBHOOK_") for name in env)
    assert all(job["metadata"]["name"].endswith("-flow-metrics-reconcile") for job in capture_jobs(documents))
    assert not [d for d in documents if d["kind"] == "Secret"]
    for job in capture_jobs(documents) + sample_jobs(documents):
        job_env = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["env"] if job["kind"] == "CronJob" else job["spec"]["template"]["spec"]["containers"][0]["env"]
        assert not any(entry["name"].startswith("FLOW_METRICS_WEBHOOK_") for entry in job_env)


def test_capture_jobs_have_exact_commands_bounds_security_and_least_credentials(helm):
    credentials = tuple(
        f"app.deployment.env.{name}=generated-{name.lower()}"
        for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST", "POSTGRES_PORT",
                     "GITHUB_APP_CLIENT_ID", "GITHUB_APP_PRIVATE_KEY", "GITHUB_APP_INSTALLATION_ID")
    )
    documents = render(helm, settings=CAPTURE_SETTINGS + credentials)
    jobs = capture_jobs(documents)
    assert len(jobs) == 1
    for job in jobs:
        collector = job["metadata"]["name"].endswith("-flow-metrics-reconcile")
        spec = job["spec"]
        assert spec["schedule"] == ("30 9,11,13,15,17 * * 1-5" if collector else "* * * * *")
        assert spec["timeZone"] == ("Europe/London" if collector else "Etc/UTC")
        assert spec["concurrencyPolicy"] == "Forbid"
        assert spec["startingDeadlineSeconds"] == 300
        assert spec["failedJobsHistoryLimit"] == 3
        assert spec["successfulJobsHistoryLimit"] == 1
        template = spec["jobTemplate"]["spec"]
        assert template["backoffLimit"] == 0
        assert template["activeDeadlineSeconds"] == (3600 if collector else 120)
        pod = template["template"]["spec"]
        assert pod["automountServiceAccountToken"] is False
        assert pod["restartPolicy"] == "Never"
        assert pod["serviceAccountName"] == "cd-serviceaccount"
        assert pod["securityContext"] == {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}}
        container, = pod["containers"]
        assert container["image"] == "synthetic/hub:generated-test"
        assert container["command"] == ["python3", "-m", "flask"]
        assert container["args"] == ["--app", "app.app", "flow-metrics"] + (
            ["collect"] if collector else ["process-deliveries", "--limit", "100"]
        )
        assert container["securityContext"] == {
            "allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]},
            "runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"},
        }
        env = {entry["name"]: entry["value"] for entry in container["env"]}
        expected_names = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST", "POSTGRES_PORT"}
        if collector:
            expected_names |= {"GITHUB_APP_CLIENT_ID", "GITHUB_APP_PRIVATE_KEY", "GITHUB_APP_INSTALLATION_ID"}
        assert set(env) == expected_names | {"SENTRY_ENV"}
        assert all(env[key] == f"generated-{key.lower()}" for key in expected_names)
        assert env["SENTRY_ENV"] == "development"
        assert len(job["metadata"]["name"]) <= 52
    original_jobs = [d for d in render(helm, settings=credentials)
                     if d["kind"] == "CronJob" and "-flow-metrics-" not in d["metadata"]["name"]]
    assert [d for d in documents if d["kind"] == "CronJob" and d not in jobs] == original_jobs


@pytest.mark.parametrize("environment,namespace", [
    ("prod", "github-community-prod"), ("dev", "github-community-prod"),
    ("prod", "github-community-dev"),
])
def test_capture_activation_fails_outside_dev(helm, environment, namespace):
    with pytest.raises(subprocess.CalledProcessError) as error:
        render(helm, environment, settings=CAPTURE_SETTINGS, namespace=namespace)
    assert "Flow Metrics capture is DEV only" in error.value.stderr


@pytest.mark.parametrize("setting", [
    "app.flowMetrics.webhook.enabled=true",
    "app.jobs.flow_metrics_process_deliveries.enabled=true",
])
@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_deferred_receiver_and_processor_cannot_be_enabled(helm, setting, environment):
    with pytest.raises(subprocess.CalledProcessError) as error:
        render(helm, environment, settings=(setting,))
    assert "deferred to Phase 3" in error.value.stderr


def test_collector_long_name_and_combined_workspace(helm):
    settings = CAPTURE_SETTINGS
    documents = render(helm, settings=settings, release="generated-long-release-name-for-flow-metrics-test")
    jobs = capture_jobs(documents)
    assert len(jobs) == 1
    assert all(len(job["metadata"]["name"]) <= 52 for job in jobs)
    deployment, = [d for d in documents if d["kind"] == "Deployment"]
    env = {entry["name"]: entry for entry in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert "FLOW_METRICS_WEBHOOK_ENABLED" not in env
    assert env["FLOW_METRICS_ENABLED"]["value"] == "true"
    assert env["FLOW_METRICS_DATA_MODE"]["value"] == "sample"


@pytest.mark.parametrize("environment,settings", [
    ("dev", ()), ("prod", ()), ("dev", CAPTURE_SETTINGS),
    ("dev", ("app.jobs.flow_metrics_reconcile.enabled=false",)),
])
def test_chart_lint(helm, environment, settings):
    command = [
        helm, "lint", "--strict", str(CHART),
        "-f", str(CHART / f"values-{environment}.yaml"),
        "--namespace", f"github-community-{environment}",
        "--set", "app.deployment.image.repository=synthetic/hub",
        "--set", "app.deployment.image.tag=generated-test",
    ]
    for setting in settings:
        command.extend(["--set", setting])
    subprocess.run(command, check=True, capture_output=True, text=True)
