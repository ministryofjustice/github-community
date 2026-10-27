"""Resolve organisation installations without choosing a project's configuration."""

from dataclasses import dataclass


DEFAULT_ORGANISATION = "ministryofjustice"


@dataclass(frozen=True)
class OrganisationInstallation:
    organisation: str
    installation_id: int


def parse_organisation_installations(
    value: str | None,
    default_installation_id: int | None,
    *,
    configuration_name: str = "GITHUB_ORGANISATIONS",
    default_organisation: str = DEFAULT_ORGANISATION,
) -> list[OrganisationInstallation]:
    value = (value or "").strip()
    if not value:
        if not default_installation_id:
            raise ValueError("GITHUB_APP_INSTALLATION_ID must be set")
        return [
            OrganisationInstallation(default_organisation, int(default_installation_id))
        ]

    result = []
    for item in value.split(","):
        organisation, separator, installation_id = item.strip().partition(":")
        organisation, installation_id = organisation.strip(), installation_id.strip()
        if not separator or not organisation or not installation_id.isdigit():
            raise ValueError(
                f"{configuration_name} must look like "
                '"organisation:installation_id,..."'
            )
        if any(existing.organisation == organisation for existing in result):
            raise ValueError(f"{configuration_name} lists {organisation} twice")
        result.append(OrganisationInstallation(organisation, int(installation_id)))
    return result
