from app.projects.repository_standards.models.owner import Owner

owners_config = [
    # Business Units
    Owner(name="HMPPS", teams=["HMPPS Developers"], prefix="hmpps-"),
    Owner(
        name="LAA",
        teams=[
            "LAA Admins",
            "LAA Technical Architects",
            "LAA Developers",
            "LAA Crime Apps team",
            "LAA Crime Apply",
            "laa-eligibility-platform",
            "LAA Get Access",
            "LAA Payments and Billing",
            "payforlegalaid",
        ],
        prefix="laa-",
    ),
    Owner(name="OPG", teams=["OPG"], prefix="opg-"),
    Owner(name="CICA", teams=["CICA"], prefix="cica-"),
    Owner(
        name="Central Digital",
        teams=[
            "Central Digital Product Team",
            "tactical-products",
            "Form Builder",
            "Hale platform",
            "JOTW Content Devs",
            "MOJDS Maintainers",
            "MOJDS Admins",
        ],
        prefix="bichard7",
    ),
    Owner(
        name="Platforms",
        teams=[
            "Platforms",
            "hosting-migrations",
            "aws-root-account-admin-team",
            "WebOps",
            "Studio Webops",
            "analytical-platform",
            "data-engineering",
            "analytics-hq",
            "data-catalogue",
            "data-platform",
            "data-and-analytics-engineering",
            "observability-platform",
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
            "WebOps",
        ],
    ),
]
