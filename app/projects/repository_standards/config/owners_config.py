from app.projects.repository_standards.models.owner import Owner

owners_config = [
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
            "analytical-platform",
            "data-engineering",
            "analytics-hq",
            "data-catalogue",
            "data-platform",
            "data-and-analytics-engineering",
            "observability-platform",
            "Form Builder",
            "Hale platform",
            "JOTW Content Devs",
        ],
        prefix="bichard7",
    ),
    Owner(
        name="Platforms",
        teams=[
            "modernisation-platform",
            "operations-engineering",
            "aws-root-account-admin-team",
            "WebOps",
            "Studio Webops",
        ],
    ),
    Owner(
        name="Technology Services",
        teams=[
            "nvvs-devops-admins",
            "moj-official-techops",
            "cloud-ops-alz-admins",
            "technology-services"
        ],
    ),
]
