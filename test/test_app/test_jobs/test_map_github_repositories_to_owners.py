import unittest
from unittest.mock import MagicMock, call, patch
from types import SimpleNamespace
from app.projects.repository_standards.jobs.map_github_repositories_to_owners import (
    main,
)
from flask import Flask
from app.projects.repository_standards.db_models import db
from app.projects.repository_standards.models.repository_info import (
    RepositoryAccess,
    RepositoryInfo,
    BasicRepositoryInfo,
)
from app.projects.repository_standards.repositories.owner_repository import (
    OwnerView,
)

from app.projects.repository_standards.models.owner import OwnerConfig

test_owner_id = 1


@patch(
    "app.projects.repository_standards.services.github_service.GithubService.__new__"
)
@patch("app.projects.repository_standards.services.asset_service.AssetService.__new__")
<<<<<<< HEAD
@patch(
    "app.projects.repository_standards.repositories.owner_repository.OwnerRepository.__new__"
)
@patch(
    "app.projects.repository_standards.services.repository_compliance_service.RepositoryComplianceService.__new__"
)
@patch(
    "app.projects.repository_standards.jobs.map_github_repositories_to_owners.owners_config",
    [Owner(name="Test Owners", teams=["Test Team"], prefix="test-prefix")],
)
=======
@patch("app.projects.repository_standards.services.owner_service.OwnerService.__new__")
>>>>>>> e8947039dc28c0d2962f2b72f6100ba28e7d522b
class TestMain(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()

    def test_when_team_has_direct_admin_access_then_admin_relationship_created(
        self,
<<<<<<< HEAD
        mock_repository_compliance_service: MagicMock,
        mock_owner_repository: MagicMock,
=======
        mock_owner_service: MagicMock,
>>>>>>> e8947039dc28c0d2962f2b72f6100ba28e7d522b
        mock_asset_service: MagicMock,
        mock_github_service: MagicMock,
    ):
        mock_repository = RepositoryInfo(
            basic=BasicRepositoryInfo(
                name="Test Repository",
                visibility="public",
                delete_branch_on_merge=False,
                default_branch_name="main",
                description="Test Description",
            ),
            access=RepositoryAccess(
                teams_with_admin=["Test Team"],
                teams_with_admin_parents=[],
                teams=[],
                teams_parents=[],
            ),
        )

        mock_github_service.return_value.get_repositories.return_value = [
            mock_repository
        ]
        mock_owner_service.return_value.find_all.return_value = [
            OwnerView(
                id=1,
                name="Test Owners",
                type="1",
                config=OwnerConfig(
                    name="Test Owners", teams=["Test Team"], prefix="test-prefix"
                ),
            )
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_service.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset
        mock_repository_compliance_service.return_value.get_repository_by_name.return_value = (
            SimpleNamespace(maturity_level=1)
        )

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        self.assertEqual(
            mock_asset_service.return_value.update_asset_by_name.call_count,
            2,
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "ADMIN_ACCESS")]
        )
        mock_github_service.return_value.set_repository_standard_custom_property.assert_has_calls(
            [call(mock_repository.basic.name, "baseline")]
        )

    def test_when_parent_team_has_admin_access_then_admin_relationship_created(
        self,
<<<<<<< HEAD
        mock_repository_compliance_service: MagicMock,
        mock_owner_repository: MagicMock,
=======
        mock_owner_service: MagicMock,
>>>>>>> e8947039dc28c0d2962f2b72f6100ba28e7d522b
        mock_asset_service: MagicMock,
        mock_github_service: MagicMock,
    ):
        mock_repository = RepositoryInfo(
            basic=BasicRepositoryInfo(
                name="Test Repository",
                visibility="public",
                delete_branch_on_merge=False,
                default_branch_name="main",
                description="Test Description",
            ),
            access=RepositoryAccess(
                teams_with_admin=[],
                teams_with_admin_parents=["Test Team"],
                teams=[],
                teams_parents=[],
            ),
        )

        mock_github_service.return_value.get_repositories.return_value = [
            mock_repository
        ]
        mock_owner_service.return_value.find_all.return_value = [
            OwnerView(
                id=1,
                name="Test Owners",
                type="1",
                config=OwnerConfig(
                    name="Test Owners", teams=["Test Team"], prefix="test-prefix"
                ),
            )
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_service.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset
        mock_repository_compliance_service.return_value.get_repository_by_name.return_value = (
            SimpleNamespace(maturity_level=1)
        )

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        self.assertEqual(
            mock_asset_service.return_value.update_asset_by_name.call_count,
            2,
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "ADMIN_ACCESS")]
        )

    def test_when_team_has_any_access_then_default_relationship_created(
        self,
<<<<<<< HEAD
        mock_repository_compliance_service: MagicMock,
        mock_owner_repository: MagicMock,
=======
        mock_owner_service: MagicMock,
>>>>>>> e8947039dc28c0d2962f2b72f6100ba28e7d522b
        mock_asset_service: MagicMock,
        mock_github_service: MagicMock,
    ):
        mock_repository = RepositoryInfo(
            basic=BasicRepositoryInfo(
                name="Test Repository",
                visibility="public",
                delete_branch_on_merge=False,
                default_branch_name="main",
                description="Test Description",
            ),
            access=RepositoryAccess(
                teams_with_admin=[],
                teams_with_admin_parents=[],
                teams=["Test Team"],
                teams_parents=[],
            ),
        )

        mock_github_service.return_value.get_repositories.return_value = [
            mock_repository
        ]
        mock_owner_service.return_value.find_all.return_value = [
            OwnerView(
                id=1,
                name="Test Owners",
                type="1",
                config=OwnerConfig(
                    name="Test Owners", teams=["Test Team"], prefix="test-prefix"
                ),
            )
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_service.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset
        mock_repository_compliance_service.return_value.get_repository_by_name.return_value = (
            SimpleNamespace(maturity_level=2)
        )

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        self.assertEqual(
            mock_asset_service.return_value.update_asset_by_name.call_count,
            2,
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )
        mock_github_service.return_value.set_repository_standard_custom_property.assert_has_calls(
            [call(mock_repository.basic.name, "standard")]
        )

    def test_when_parent_team_has_any_access_then_default_relationship_created(
        self,
<<<<<<< HEAD
        mock_repository_compliance_service: MagicMock,
        mock_owner_repository: MagicMock,
=======
        mock_owner_service: MagicMock,
>>>>>>> e8947039dc28c0d2962f2b72f6100ba28e7d522b
        mock_asset_service: MagicMock,
        mock_github_service: MagicMock,
    ):
        mock_repository = RepositoryInfo(
            basic=BasicRepositoryInfo(
                name="Test Repository",
                visibility="public",
                delete_branch_on_merge=False,
                default_branch_name="main",
                description="Test Description",
            ),
            access=RepositoryAccess(
                teams_with_admin=[],
                teams_with_admin_parents=[],
                teams=[],
                teams_parents=["Test Team"],
            ),
        )

        mock_github_service.return_value.get_repositories.return_value = [
            mock_repository
        ]
        mock_owner_service.return_value.find_all.return_value = [
            OwnerView(
                id=1,
                name="Test Owners",
                type="1",
                config=OwnerConfig(
                    name="Test Owners", teams=["Test Team"], prefix="test-prefix"
                ),
            )
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_service.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset
        mock_repository_compliance_service.return_value.get_repository_by_name.return_value = (
            SimpleNamespace(maturity_level=1)
        )

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        self.assertEqual(
            mock_asset_service.return_value.update_asset_by_name.call_count,
            2,
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )

    def test_when_prefix_matches_repository_name_then_default_relationship_created(
        self,
<<<<<<< HEAD
        mock_repository_compliance_service: MagicMock,
        mock_owner_repository: MagicMock,
=======
        mock_owner_service: MagicMock,
>>>>>>> e8947039dc28c0d2962f2b72f6100ba28e7d522b
        mock_asset_service: MagicMock,
        mock_github_service: MagicMock,
    ):
        mock_repository = RepositoryInfo(
            basic=BasicRepositoryInfo(
                name="test-prefix Test Repository",
                visibility="public",
                delete_branch_on_merge=False,
                default_branch_name="main",
                description="Test Description",
            ),
            access=RepositoryAccess(
                teams_with_admin=[],
                teams_with_admin_parents=[],
                teams=["Test Team"],
                teams_parents=[],
            ),
        )

        mock_github_service.return_value.get_repositories.return_value = [
            mock_repository
        ]
        mock_owner_service.return_value.find_all.return_value = [
            OwnerView(
                id=1,
                name="Test Owners",
                type="1",
                config=OwnerConfig(
                    name="Test Owners", teams=["Test Team"], prefix="test-prefix"
                ),
            )
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_service.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset
        mock_repository_compliance_service.return_value.get_repository_by_name.return_value = (
            SimpleNamespace(maturity_level=0)
        )

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        self.assertEqual(
            mock_asset_service.return_value.update_asset_by_name.call_count,
            2,
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )
        mock_github_service.return_value.set_repository_standard_custom_property.assert_not_called()

    def test_when_no_matches_then_no_relationships_created(
        self,
        mock_owner_service: MagicMock,
        mock_asset_service: MagicMock,
        mock_github_service: MagicMock,
    ):
        mock_repository = RepositoryInfo(
            basic=BasicRepositoryInfo(
                name="NOTHING MATCHES THIS",
                visibility="public",
                delete_branch_on_merge=False,
                default_branch_name="main",
                description="Test Description",
            ),
            access=RepositoryAccess(
                teams_with_admin=[],
                teams_with_admin_parents=[],
                teams=["NO TEAM MATCHES THIS"],
                teams_parents=[],
            ),
        )

        mock_github_service.return_value.get_repositories.return_value = [
            mock_repository
        ]
        mock_owner_service.return_value.find_all.return_value = [
            OwnerView(
                id=1,
                name="Test Owners",
                type="1",
                config=OwnerConfig(
                    name="Test Owners", teams=["Test Team"], prefix="test-prefix"
                ),
            )
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_service.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict())]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
