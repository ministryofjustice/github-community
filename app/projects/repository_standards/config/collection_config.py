"""Organisation installations used by the Repository Standards collector."""

from app.shared.services.github_collection_config import (
    DEFAULT_ORGANISATION as DEFAULT_ORGANISATION,
    OrganisationInstallation as OrganisationInstallation,
    parse_organisation_installations as parse_installations,
)


def parse_organisation_installations(
    value: str | None, default_installation_id: int | None
) -> list[OrganisationInstallation]:
    return parse_installations(
        value,
        default_installation_id,
        configuration_name="GITHUB_REPOSITORY_STANDARDS_ORGS",
    )
