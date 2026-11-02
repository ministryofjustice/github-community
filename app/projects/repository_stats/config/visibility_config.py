import os

# TO CONFIRM: the date archived public repositories must be made internal by.
VISIBILITY_ARCHIVED_DEADLINE = (
    os.getenv("VISIBILITY_ARCHIVED_DEADLINE") or "23 October 2026"
)

VISIBILITY_SLACK_CHANNEL_NAME = "#ask-developer-experience"
VISIBILITY_SLACK_CHANNEL_URL = "https://moj.enterprise.slack.com/archives/C0AJBK3P5A8"
