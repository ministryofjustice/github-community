"""Render-only Helm checks; never contact Kubernetes or use real credentials."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART = Path("helm/github-community")


@pytest.fixture
def helm():
    executable = os.environ.get("HELM_BINARY") or shutil.which("helm")
    if not executable:
        pytest.skip("Helm is required for chart rendering checks.")
    return executable


def render(helm, environment="dev", settings=(), upgrade=False, release="github-community"):
    command = [
        helm, "template", release, str(CHART),
        "-f", str(CHART / f"values-{environment}.yaml"),
        "--set", "app.deployment.image.repository=synthetic/hub",
        "--set", "app.deployment.image.tag=generated-test",
    ]
    if upgrade:
        command.append("--is-upgrade")
    for setting in settings:
        command.extend(["--set" if setting.startswith("app.jobs.") else "--set-string", setting])
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
def test_optional_flow_environment_is_absent_by_default(helm, environment):
    deployment, = [d for d in render(helm, environment) if d["kind"] == "Deployment"]
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    assert not [entry for entry in env if entry["name"].startswith("FLOW_METRICS_")]
    assert not [entry for entry in env if entry["name"] == "AUTH_ENABLED"]


def test_explicit_flow_environment_is_quoted_and_does_not_enter_job(helm):
    expected = {
        "FLOW_METRICS_ENABLED": "false",
        "FLOW_METRICS_DATA_MODE": "sample",
        "FLOW_METRICS_WORKSPACE_NAME": "Generated workspace",
        "FLOW_METRICS_SOURCE_URL": "https://github.com/orgs/example/projects/42",
    }
    documents = render(helm, settings=tuple(
        f"app.deployment.env.{name}={value}" for name, value in expected.items()
    ))
    deployment, = [d for d in documents if d["kind"] == "Deployment"]
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    actual = {entry["name"]: entry.get("value") for entry in env}
    assert all(actual[name] == value for name, value in expected.items())
    job, = sample_jobs(documents)
    job_env = job["spec"]["template"]["spec"]["containers"][0]["env"]
    assert not [entry for entry in job_env if entry["name"].startswith("FLOW_METRICS_")]
