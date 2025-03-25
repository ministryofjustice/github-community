import unittest
from unittest.mock import MagicMock, call, patch
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
from app.projects.repository_standards.models.owner import Owner

test_owner_id = 1


@patch(
    "app.projects.repository_standards.services.github_service.GithubService.__new__"
)
@patch("app.projects.repository_standards.services.asset_service.AssetService.__new__")
@patch(
    "app.projects.repository_standards.repositories.owner_repository.OwnerRepository.__new__"
)
@patch(
    "app.projects.repository_standards.jobs.map_github_repositories_to_owners.owners_config",
    [Owner(name="Test Owners", teams=["Test Team"], prefix="test-prefix")],
)
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
        mock_owner_repository: MagicMock,
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

        mock_github_service.return_value.get_all_repositories.return_value = [
            mock_repository
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset

        with self.app.app_context():
            main()

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict())]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "ADMIN_ACCESS")]
        )

    def test_when_parent_team_has_admin_access_then_admin_relationship_created(
        self,
        mock_owner_repository: MagicMock,
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

        mock_github_service.return_value.get_all_repositories.return_value = [
            mock_repository
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset

        with self.app.app_context():
            main()

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict())]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "ADMIN_ACCESS")]
        )

    def test_when_team_has_any_access_then_default_relationship_created(
        self,
        mock_owner_repository: MagicMock,
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

        mock_github_service.return_value.get_all_repositories.return_value = [
            mock_repository
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset

        with self.app.app_context():
            main()

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict())]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )

    def test_when_parent_team_has_any_access_then_default_relationship_created(
        self,
        mock_owner_repository: MagicMock,
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

        mock_github_service.return_value.get_all_repositories.return_value = [
            mock_repository
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset

        with self.app.app_context():
            main()

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict())]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )

    def test_when_prefix_matches_repository_name_then_default_relationship_created(
        self,
        mock_owner_repository: MagicMock,
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

        mock_github_service.return_value.get_all_repositories.return_value = [
            mock_repository
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.update_asset_by_name.return_value = mock_asset

        with self.app.app_context():
            main()

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict())]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )


if __name__ == "__main__":
    unittest.main()
