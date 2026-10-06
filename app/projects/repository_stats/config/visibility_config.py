import os

# TO CONFIRM: the date archived public repositories must be made internal by.
VISIBILITY_ARCHIVED_DEADLINE = (
    os.getenv("VISIBILITY_ARCHIVED_DEADLINE") or "23 October 2026"
)

VISIBILITY_SLACK_CHANNEL_NAME = "#ask-developer-experience"
VISIBILITY_SLACK_CHANNEL_URL = "https://moj.enterprise.slack.com/archives/C0AJBK3P5A8"

# Organisations come from whatever the snapshot data holds (the "org" column), so the
# report already covers several GitHub Enterprise organisations. Real dynamic org fetching
# from the GitHub Enterprise API, and live data collection, are deferred to M3 pending
# installation of the GitHub App on the other organisations. Until then the data is the
# local stub seed in contrib/db-init/03-stub-repository-stats-data.sql.
