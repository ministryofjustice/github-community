"""Which GitHub organisations the visibility job scans.

Each organisation needs its own GitHub App installation id, because installation tokens
are per installation. Set REPOSITORY_STATS_ORGS to scan more organisations, e.g.
"ministryofjustice:12345,moj-analytical-services:67890". When it's unset, the job scans
ministryofjustice with the app's existing GITHUB_APP_INSTALLATION_ID. The app is private,
so it can't be installed on other organisations yet; adding them later is config only.
"""

import os
from dataclasses import dataclass

DEFAULT_ORG = "ministryofjustice"
RECORD_VISIBILITY_JOB_NAME = "record_repository_visibility"


@dataclass(frozen=True)
class OrgInstallation:
    org: str
    installation_id: int


def parse_org_installations(
    value: str | None, default_installation_id: int | None
) -> list[OrgInstallation]:
    value = (value or "").strip()
    if not value:
        if not default_installation_id:
            raise ValueError("GITHUB_APP_INSTALLATION_ID must be set")
        return [OrgInstallation(DEFAULT_ORG, int(default_installation_id))]

    result: list[OrgInstallation] = []
    for item in value.split(","):
        org, separator, installation_id = item.strip().partition(":")
        org, installation_id = org.strip(), installation_id.strip()
        if not separator or not org or not installation_id.isdigit():
            raise ValueError(
                'REPOSITORY_STATS_ORGS must look like "org:installation_id,..."'
            )
        if any(existing.org == org for existing in result):
            raise ValueError("REPOSITORY_STATS_ORGS lists an organisation twice")
        result.append(OrgInstallation(org, int(installation_id)))
    return result


def org_installations(default_installation_id: int | None) -> list[OrgInstallation]:
    return parse_org_installations(
        os.getenv("REPOSITORY_STATS_ORGS"), default_installation_id
    )
