import unittest
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree

from app.projects.repository_standards.services.repository_compliance_service import (
    MOJ_CROWN_LOGO,
    RepositoryComplianceService,
)
from app.projects.repository_standards.services.technical_standard_badge import (
    get_technical_standard_badge_svg,
    get_technical_standard_badge_shield_url,
)


class TestTechnicalStandardBadge(unittest.TestCase):
    def test_report_badge_svgs_have_status_colors_labels_and_crown(self):
        badge_cases = (
            (True, "MOJ: COMPLIANT", "#cce2d8"),
            (False, "MOJ: NON-COMPLIANT", "#f4cdc6"),
        )

        for compliant, expected_title, expected_color in badge_cases:
            with self.subTest(compliant=compliant):
                badge = ElementTree.fromstring(
                    get_technical_standard_badge_svg(compliant)
                )
                title = badge.find("{http://www.w3.org/2000/svg}title")
                image = badge.find("{http://www.w3.org/2000/svg}image")
                text_nodes = badge.findall(".//{http://www.w3.org/2000/svg}text")
                fills = {
                    element.get("fill")
                    for element in badge.findall(".//{http://www.w3.org/2000/svg}rect")
                }

                self.assertEqual(title.text, expected_title)
                self.assertIn(expected_color, fills)
                self.assertEqual(
                    image.get("href"),
                    f"data:image/png;base64,{MOJ_CROWN_LOGO}",
                )
                self.assertEqual(text_nodes[0].text, "MOJ")
                self.assertIsNone(text_nodes[0].get("font-weight"))
                self.assertEqual(text_nodes[1].text, expected_title.split(": ")[1])
                self.assertEqual(text_nodes[1].get("font-weight"), "bold")
                self.assertEqual(
                    text_nodes[1].get("fill"),
                    "#005a30" if compliant else "#2a0b06",
                )

    def test_compliant_and_non_compliant_report_badges_have_equal_width(self):
        compliant_badge = ElementTree.fromstring(
            get_technical_standard_badge_svg(True)
        )
        non_compliant_badge = ElementTree.fromstring(
            get_technical_standard_badge_svg(False)
        )

        self.assertEqual(compliant_badge.get("width"), non_compliant_badge.get("width"))

    def test_compliant_badge_uses_black_moj_label_green_status_and_crown(self):
        badge_url = get_technical_standard_badge_shield_url(True, "for-the-badge")
        parsed_url = urlparse(badge_url)
        query = parse_qs(parsed_url.query)

        self.assertEqual(parsed_url.path, "/badge/MOJ-COMPLIANT-cce2d8")
        self.assertEqual(query["style"], ["for-the-badge"])
        self.assertEqual(query["labelColor"], ["0b0c0c"])
        self.assertEqual(
            query["logo"], [f"data:image/png;base64,{MOJ_CROWN_LOGO}"]
        )

    def test_non_compliant_badge_uses_red_status(self):
        badge_url = get_technical_standard_badge_shield_url(False, "flat")

        self.assertIn("/badge/MOJ-NON-COMPLIANT-f4cdc6", badge_url)
        self.assertIn("style=flat", badge_url)

    def test_unknown_repository_badge_uses_neutral_status(self):
        badge_url = get_technical_standard_badge_shield_url(None, "flat")

        self.assertIn("/badge/MOJ-NOT%20FOUND-b1b4b6", badge_url)

    def test_legacy_badge_builder_keeps_the_same_crown_logo(self):
        legacy_service = RepositoryComplianceService(asset_service=None)
        legacy_service.get_repository_by_name = lambda repository_name: None
        badge_url = legacy_service.get_repository_compliance_badge_shield_url_by_name(
            "example-repo"
        )
        logo = next(
            parameter.split("=", 1)[1]
            for parameter in urlparse(badge_url).query.split("&")
            if parameter.startswith("logo=")
        )

        self.assertEqual(logo, f"data:image/png;base64,{MOJ_CROWN_LOGO}")