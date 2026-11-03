"""Opt-in checks against Docker's actual context matcher, without a runtime image."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("FLOW_METRICS_DOCKER_CONTEXT_TEST") != "true",
    reason="Set FLOW_METRICS_DOCKER_CONTEXT_TEST=true with an existing local Docker builder.",
)
def test_context_excludes_nested_private_artifacts_and_preserves_build_assets(tmp_path):
    context = tmp_path / "input"
    output = tmp_path / "output"
    context.mkdir()
    (context / ".dockerignore").write_bytes(Path(".dockerignore").read_bytes())
    excluded = [
        ".venv/pyvenv.cfg", ".copilot/runtime.json",
        "app/nested/.venv/pyvenv.cfg", "app/nested/.copilot/runtime.json",
        "app/nested/__pycache__/module.cpython-313.pyc",
        "app/nested/module.pyc", "migrations/nested/module.pyo",
        "test/.pytest_cache/README.md", "app/.ruff_cache/state",
        "app/.env", "app/nested/.env.local", "app/nested/daily.log.1",
        "app/nested/data.sqlite3", "app/nested/data.sqlite3-wal", "app/nested/database.db",
        "app/nested/database.dump", "app/nested/database.sql.gz",
        "app/nested/credential.key", "app/nested/credential.pem",
        "app/nested/credential.p12", "app/nested/credential.pfx",
        "app/nested/archives/record.json", "app/nested/snapshots/record.json",
        "app/nested/private-runtime/config.json", "app/FlowMetrics/config.json",
        "app/acceptance-checks/record.json", "app/nested/capture.json",
        "app/nested/board-snapshot.json", "app/nested/project-152-generated.json",
        "app/nested/health.json", "app/nested/config.local.json",
    ]
    retained = [
        "app/projects/flow_metrics/sample-seed.json",
        "app/projects/flow_metrics/README.md",
        "app/static/projects/flow_metrics/vendor/chart.umd.js",
        "app/static/projects/flow_metrics/vendor/LICENSE.md",
        "app/static/projects/flow_metrics/javascript/flow-metrics.js",
        "app/templates/projects/flow_metrics/pages/main.html",
        "app/static/images/govuk-icon-192.png",
        "migrations/versions/generated.py",
        "uv.lock", "pyproject.toml", "container/usr/local/bin/entrypoint.sh",
    ]
    for relative in excluded + retained:
        target = context / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("Generated context marker, not private data.\n")
    completed = subprocess.run(
        ["docker", "buildx", "build", "--network=none", "--provenance=false",
         "--file=-", f"--output=type=local,dest={output}", str(context)],
        input="FROM scratch\nCOPY . /context\n", text=True,
        capture_output=True, timeout=120, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert all(not (output / "context" / relative).exists() for relative in excluded)
    assert all((output / "context" / relative).is_file() for relative in retained)
