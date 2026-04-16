import unittest

from app.projects.repository_standards.config.repository_compliance_config import (
    BASELINE,
    STANDARD,
    EXEMPLAR,
    get_repository_standard_from_maturity_level,
)


class TestRepositoryComplianceConfig(unittest.TestCase):
    def test_maps_baseline_maturity_to_repository_standard(self):
        self.assertEqual(
            get_repository_standard_from_maturity_level(BASELINE),
            "baseline",
        )

    def test_maps_standard_maturity_to_repository_standard(self):
        self.assertEqual(
            get_repository_standard_from_maturity_level(STANDARD),
            "standard",
        )

    def test_maps_exemplar_maturity_to_repository_standard(self):
        self.assertEqual(
            get_repository_standard_from_maturity_level(EXEMPLAR),
            "exemplar",
        )

    def test_returns_none_when_maturity_level_is_not_mapped(self):
        self.assertIsNone(get_repository_standard_from_maturity_level(0))


if __name__ == "__main__":
    unittest.main()
