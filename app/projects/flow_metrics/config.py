import os
import re

DEFAULT_SOURCE_URL = "https://github.com/orgs/ministryofjustice/projects/152"


def workspace_config():
    mode = os.getenv("FLOW_METRICS_DATA_MODE", "sample")
    name = os.getenv("FLOW_METRICS_WORKSPACE_NAME", "Developer Experience").strip()
    source_url = os.getenv("FLOW_METRICS_SOURCE_URL", DEFAULT_SOURCE_URL)
    if mode not in {"sample", "real"}:
        raise ValueError("FLOW_METRICS_DATA_MODE must be sample or real.")
    if not name or len(name) > 80:
        raise ValueError("FLOW_METRICS_WORKSPACE_NAME must contain 1 to 80 characters.")
    if not re.fullmatch(
        r"https://github\.com/orgs/[A-Za-z0-9-]+/projects/[1-9][0-9]*", source_url
    ):
        raise ValueError("FLOW_METRICS_SOURCE_URL must be a GitHub organisation project URL.")
    if mode == "real" and source_url != DEFAULT_SOURCE_URL:
        raise ValueError("The real collector currently supports only project 152.")
    if mode == "real" and os.getenv("FLOW_METRICS_ENABLED") != "true":
        raise ValueError("Real mode requires FLOW_METRICS_ENABLED=true.")
    return {"live": mode == "real", "workspace_name": name, "source_url": source_url}
