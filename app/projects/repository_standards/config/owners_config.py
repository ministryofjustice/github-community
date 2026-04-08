from app.projects.repository_standards.models.owner import Owner

owners_config = [
    # Business Units
    Owner(name="HMPPS", teams=["hmpps-developers"], prefix="hmpps-"),
    Owner(
        name="LAA",
        teams=[
            "laa-admins",
            "laa-technical-architects",
            "laa-developers",
            "laa-crime-apps-team",
            "laa-crime-apply",
            "laa-eligibility-platform",
            "laa-get-access",
            "laa-payments-and-billing",
            "payforlegalaid",
        ],
        prefix="laa-",
    ),
    Owner(name="OPG", teams=["opg"], prefix="opg-"),
    Owner(name="CICA", teams=["cica"], prefix="cica-"),
    Owner(
        name="Central Digital",
        teams=[
            "central-digital-product-team",
            "tactical-products",
            "form-builder",
            "hale-platform",
            "jotw-content-devs",
            "mojds-maintainers",
            "mojds-admins",
        ],
        prefix="bichard7",
    ),
    Owner(
        name="Platforms",
        teams=[
            "platforms",
            "hosting-migrations",
            "aws-root-account-admin-team",
            "webops",
            "studio-webops",
            "analytical-platform",
            "data-engineering",
            "analytics-hq",
            "data-catalogue",
            "data-platform",
            "data-and-analytics-engineering",
            "observability-platform",
            "dev-sec-ops",
        ],
    ),
    Owner(
        name="Technology Services",
        teams=[
            "nvvs-devops-admins",
            "moj-official-techops",
            "cloud-ops-alz-admins",
            "Technology Services",
        ],
    ),
    # Teams
    Owner(
        name="Modernisation Platform",
        teams=[
            "modernisation-platform",
        ],
    ),
    Owner(
        name="GitHub Community",
        teams=[
            "github-community",
        ],
    ),
    Owner(
        name="Cloud Platform",
        teams=[
            "webops",
        ],
    ),
]
