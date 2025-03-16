import unittest
from unittest.mock import MagicMock, call, patch
from app.projects.repository_standards.jobs.map_github_repositories_to_owners import (
    main,
)
from flask import Flask
from app.projects.repository_standards.db_models import db

test_owner_id = 1


@patch("app.projects.repository_standards.services.github_service.GithubService.__new__")
@patch("app.projects.repository_standards.services.asset_service.AssetService.__new__")
@patch("app.projects.repository_standards.repositories.owner_repository.OwnerRepository.__new__")
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
        mock_github_service.return_value.get_all_repositories.return_value = [
            {
                "name": "Test Repository",
                "github_teams_with_admin_access": ["Admin Team"],
                "github_teams_with_any_access": [],
                "github_teams_with_admin_access_parents": [],
                "github_teams_with_any_access_parents": [],
            },
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.add_if_name_does_not_exist.return_value = (
            mock_asset
        )

        with self.app.app_context():
            main(
                owners=[{"name": "Test Owners", "teams": ["Admin Team"]}],
            )

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.add_if_name_does_not_exist.assert_has_calls(
            [call("Test Repository")]
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
        mock_github_service.return_value.get_all_repositories.return_value = [
            {
                "name": "Test Repository",
                "github_teams_with_admin_access": [],
                "github_teams_with_any_access": [],
                "github_teams_with_admin_access_parents": ["Admin Team"],
                "github_teams_with_any_access_parents": [],
            },
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.add_if_name_does_not_exist.return_value = (
            mock_asset
        )

        with self.app.app_context():
            main(
                owners=[{"name": "Test Owners", "teams": ["Admin Team"]}],
            )

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.add_if_name_does_not_exist.assert_has_calls(
            [call("Test Repository")]
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
        mock_github_service.return_value.get_all_repositories.return_value = [
            {
                "name": "Test Repository",
                "github_teams_with_admin_access": [],
                "github_teams_with_any_access": ["Test Team"],
                "github_teams_with_admin_access_parents": [],
                "github_teams_with_any_access_parents": [],
            },
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.add_if_name_does_not_exist.return_value = (
            mock_asset
        )

        with self.app.app_context():
            main(
                owners=[{"name": "Test Owners", "teams": ["Test Team"]}],
            )

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.add_if_name_does_not_exist.assert_has_calls(
            [call("Test Repository")]
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
        mock_github_service.return_value.get_all_repositories.return_value = [
            {
                "name": "Test Repository",
                "github_teams_with_admin_access": [],
                "github_teams_with_any_access": [],
                "github_teams_with_admin_access_parents": [],
                "github_teams_with_any_access_parents": ["Test Team"],
            },
        ]

        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.add_if_name_does_not_exist.return_value = (
            mock_asset
        )

        with self.app.app_context():
            main(
                owners=[{"name": "Test Owners", "teams": ["Test Team"]}],
            )

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.add_if_name_does_not_exist.assert_has_calls(
            [call("Test Repository")]
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
        mock_github_service.return_value.get_all_repositories.return_value = [
            {
                "name": "test-prefix-Test Repository",
                "github_teams_with_admin_access": [],
                "github_teams_with_any_access": [],
                "github_teams_with_admin_access_parents": [],
                "github_teams_with_any_access_parents": [],
            },
        ]
        mock_asset = MagicMock()
        mock_owner = MagicMock()
        mock_owner_repository.return_value.find_by_name.return_value = [mock_owner]
        mock_asset_service.return_value.add_if_name_does_not_exist.return_value = (
            mock_asset
        )

        with self.app.app_context():
            main(
                owners=[
                    {
                        "name": "Test Owners",
                        "teams": ["Test Team"],
                        "prefix": "test-prefix-",
                    }
                ],
            )

        mock_owner_repository.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.add_if_name_does_not_exist.assert_has_calls(
            [call("test-prefix-Test Repository")]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )


if __name__ == "__main__":
    unittest.main()
