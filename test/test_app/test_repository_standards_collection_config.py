import unittest

from app.projects.repository_standards.config.collection_config import (
    OrganisationInstallation,
    parse_organisation_installations,
)


class TestOrganisationInstallations(unittest.TestCase):
    def test_defaults_to_existing_ministry_installation(self):
        self.assertEqual(
            parse_organisation_installations(None, 123),
            [OrganisationInstallation("ministryofjustice", 123)],
        )

    def test_parses_multiple_org_installations(self):
        self.assertEqual(
            parse_organisation_installations(
                "ministryofjustice:123, moj-analytical-services:456", 999
            ),
            [
                OrganisationInstallation("ministryofjustice", 123),
                OrganisationInstallation("moj-analytical-services", 456),
            ],
        )

    def test_rejects_malformed_or_duplicate_orgs(self):
        for value in ("ministryofjustice", "ministryofjustice:nope", "org:1,org:2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_organisation_installations(value, 123)