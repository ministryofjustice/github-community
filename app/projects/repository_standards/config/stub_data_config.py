from app.projects.repository_standards.repositories.owner_repository import (
    get_owner_repository,
)
from app.projects.repository_standards.services.asset_service import get_asset_service


def create_stub_data(app):
    admin_access = "STUBBED - Admin Access"
    asset_type = "STUBBED - GitHub Repository"

    with app.app_context():
        asset_service = get_asset_service()
        owner_repository = get_owner_repository()

        asset_service.clean_all_tables()

        hmpps = owner_repository.add_owner("STUBBED - HMPPS")
        opg = owner_repository.add_owner("STUBBED - OPG")
        laa = owner_repository.add_owner("STUBBED - LAA")

        operations_engineering = asset_service.add_asset(
            "operations-engineering",
            asset_type,
            data={
                "basic": {
                    "name": "operations-engineering",
                    "license": "mit",
                    "default_branch_name": "master",
                    "visibility": "public",
                    "description": None,
                    "delete_branch_on_merge": None,
                },
                "access": {
                    "teams": [
                        "operations-engineering",
                    ],
                    "teams_parents": ["technical-architects"],
                    "teams_with_admin": [
                        "operations-engineering",
                    ],
                    "teams_with_admin_parents": ["technical-architects"],
                },
                "security_and_analysis": {
                    "advanced_security": None,
                    "non_provider_patterns": "enabled",
                    "push_protection_status": "enabled",
                    "secret_scanning_status": "enabled",
                    "secret_scanning_validity_checks": None,
                },
                "default_branch_protection": {
                    "enabled": None,
                    "enforce_admins": True,
                    "allow_force_pushes": False,
                    "required_signatures": False,
                    "dismiss_stale_reviews": True,
                    "require_code_owner_reviews": True,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 2,
                },
            },
        )
        asset_service.create_relationship(operations_engineering, hmpps, admin_access)

        opg_data = asset_service.add_asset(
            "opg-data",
            asset_type,
            data={
                "basic": {
                    "name": "opg-data",
                    "license": "mit",
                    "default_branch_name": "main",
                    "visibility": "public",
                    "description": "OPG Data repository",
                    "delete_branch_on_merge": None,
                },
                "access": {
                    "teams": [
                        "operations-engineering",
                    ],
                    "teams_parents": ["technical-architects"],
                    "teams_with_admin": [
                        "operations-engineering",
                    ],
                    "teams_with_admin_parents": ["technical-architects"],
                },
                "security_and_analysis": {
                    "advanced_security": None,
                    "non_provider_patterns": "disabled",
                    "push_protection_status": "disabled",
                    "secret_scanning_status": "enabled",
                    "secret_scanning_validity_checks": None,
                },
                "default_branch_protection": {
                    "enabled": None,
                    "enforce_admins": True,
                    "allow_force_pushes": False,
                    "required_signatures": False,
                    "dismiss_stale_reviews": True,
                    "require_code_owner_reviews": True,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 2,
                },
            },
        )
        asset_service.create_relationship(opg_data, opg, admin_access)

        cla_public = asset_service.add_asset(
            "cla_public",
            asset_type,
            data={
                "basic": {
                    "name": "cla_public",
                    "license": "mit",
                    "default_branch_name": "main",
                    "visibility": "public",
                    "description": "CLA Public repository",
                    "delete_branch_on_merge": None,
                },
                "access": {
                    "teams": [
                        "HMPPS Developers",
                    ],
                    "teams_parents": ["technical-architects"],
                    "teams_with_admin": [
                        "HMPPS Developers",
                    ],
                    "teams_with_admin_parents": ["technical-architects"],
                },
            },
        )
        asset_service.create_relationship(cla_public, laa, admin_access)
