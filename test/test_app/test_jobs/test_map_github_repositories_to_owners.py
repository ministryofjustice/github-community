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
from app.projects.repository_standards.repositories.owner_repository import (
    OwnerView,
)

from app.projects.repository_standards.models.owner import OwnerConfig

test_owner_id = 1


@patch(
    "app.projects.repository_standards.jobs.map_github_repositories_to_owners.GithubService"
)
@patch("app.projects.repository_standards.jobs.map_github_repositories_to_owners.AssetService")
@patch("app.projects.repository_standards.jobs.map_github_repositories_to_owners.OwnerService")
class TestMain(unittest.TestCase):
    def test_save_failure_does_not_cleanup_or_start_the_next_organisation(
        self, mock_owner_service, mock_asset_service, mock_github_service
    ):
        mock_owner_service.return_value.find_all.return_value = []
        mock_github_service.return_value.get_repositories.return_value = [MagicMock()]
        mock_asset_service.return_value.update_asset_by_name.side_effect = RuntimeError("database write failed")
        with (
            patch(
                "app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.repository_standards_orgs",
                "ministryofjustice:123,moj-analytical-services:456",
            ),
            self.app.app_context(),
            self.assertRaisesRegex(RuntimeError, "database write failed"),
        ):
            main()
        mock_github_service.assert_called_once()
        mock_asset_service.return_value.remove_stale_assets.assert_not_called()
        mock_asset_service.return_value.remove_stale_relationships.assert_not_called()

    def test_two_installations_save_same_named_repos_without_cross_org_ownership(
        self, mock_owner_service, mock_asset_service, mock_github_service
    ):
        repositories = [
            RepositoryInfo(
                basic=BasicRepositoryInfo(
                    name="shared", visibility="private", default_branch_name="main",
                    delete_branch_on_merge=True, organisation=organisation,
                ),
                access=RepositoryAccess(
                    teams_with_admin=["shared-team"], teams_with_admin_parents=[],
                    teams=[], teams_parents=[],
                ),
            )
            for organisation in ("ministryofjustice", "moj-analytical-services")
        ]
        owner = OwnerView(
            id=1, name="MOJ owner", type="TEAM",
            config=OwnerConfig(name="MOJ owner", teams=["shared-team"]),
        )
        mock_owner_service.return_value.find_all.return_value = [owner]
        mock_owner_service.return_value.find_by_name.return_value = [owner]
        first, second = MagicMock(), MagicMock()
        first.get_repositories.return_value = [repositories[0]]
        second.get_repositories.return_value = [repositories[1]]
        mock_github_service.side_effect = [first, second]
        with (
            patch(
                "app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.repository_standards_orgs",
                "ministryofjustice:123,moj-analytical-services:456",
            ),
            self.app.app_context(),
        ):
            main()
        self.assertEqual(
            [entry.args[2] for entry in mock_github_service.call_args_list], [123, 456]
        )
        self.assertEqual(
            [entry.kwargs["organisation_name"] for entry in mock_github_service.call_args_list],
            ["ministryofjustice", "moj-analytical-services"],
        )
        service = mock_asset_service.return_value
        self.assertEqual(service.update_asset_by_name.call_count, 2)
        self.assertEqual(
            [entry.kwargs["organisation"] for entry in service.update_asset_by_name.call_args_list],
            ["ministryofjustice", "moj-analytical-services"],
        )
        service.update_relationships_with_owner.assert_called_once()
        self.assertEqual(service.remove_stale_assets.call_args_list, [
            call(["ministryofjustice"], "public"),
            call(["moj-analytical-services"], "public"),
        ])
        second.get_repositories.assert_called_once_with(
            workers=1, visibility="public", limit=1499
        )

    def test_second_org_failure_preserves_first_org_saves_before_second_starts(
        self, mock_owner_service, mock_asset_service, mock_github_service
    ):
        mock_owner_service.return_value.find_all.return_value = []
        first_repository = MagicMock()
        service = mock_asset_service.return_value

        def collect(**kwargs):
            if mock_github_service.return_value.get_repositories.call_count == 1:
                return [first_repository]
            service.update_asset_by_name.assert_called_once()
            service.remove_stale_assets.assert_called_once_with(
                ["ministryofjustice"], "public"
            )
            service.remove_stale_relationships.assert_called_once_with(
                ["ministryofjustice"], "public"
            )
            raise RuntimeError("second org failed")

        mock_github_service.return_value.get_repositories.side_effect = collect
        with (
            patch(
                "app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.repository_standards_orgs",
                "ministryofjustice:123,moj-analytical-services:456",
            ),
            self.app.app_context(),
            self.assertRaisesRegex(RuntimeError, "second org failed"),
        ):
            main()
        service.update_asset_by_name.assert_called_once_with(
            first_repository.basic.name, first_repository.to_dict(),
            organisation=first_repository.basic.organisation,
        )
        service.remove_stale_assets.assert_called_once_with(
            ["ministryofjustice"], "public"
        )
        service.remove_stale_relationships.assert_called_once_with(
            ["ministryofjustice"], "public"
        )

    def test_capped_collection_does_not_cleanup_or_contact_unscanned_org(
        self, mock_owner_service, mock_asset_service, mock_github_service
    ):
        mock_owner_service.return_value.find_all.return_value = []
        mock_github_service.return_value.get_repositories.return_value = [MagicMock()]
        with (
            patch(
                "app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.repository_standards_orgs",
                "ministryofjustice:123,moj-analytical-services:456",
            ),
            patch(
                "app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.repository_limit", 1
            ),
            self.app.app_context(),
        ):
            main()
        mock_github_service.assert_called_once()
        mock_asset_service.return_value.update_asset_by_name.assert_called_once()
        mock_asset_service.return_value.remove_stale_assets.assert_not_called()
        mock_asset_service.return_value.remove_stale_relationships.assert_not_called()

    def setUp(self):
        installation_id = patch(
            "app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.app.installation_id",
            123,
        )
        installation_id.start()
        self.addCleanup(installation_id.stop)
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()

    def test_collection_failure_does_not_write_or_clean_up_assets(
        self, mock_owner_service, mock_asset_service, mock_github_service
    ):
        mock_owner_service.return_value.find_all.return_value = [MagicMock()]
        mock_github_service.return_value.get_repositories.side_effect = RuntimeError("Collection failed")
        with (
            patch("app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.collection_workers", 3),
            self.app.app_context(),
            self.assertRaisesRegex(RuntimeError, "Collection failed"),
        ):
            main()
        mock_github_service.return_value.get_repositories.assert_called_once_with(
            workers=3, visibility="public", limit=1500
        )
        mock_asset_service.return_value.update_asset_by_name.assert_not_called()
        mock_asset_service.return_value.remove_stale_assets.assert_not_called()
        mock_asset_service.return_value.remove_stale_relationships.assert_not_called()

    def test_when_team_has_direct_admin_access_then_admin_relationship_created(
        self,
        mock_owner_service: MagicMock,
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

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict(), organisation="ministryofjustice")]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "ADMIN_ACCESS")]
        )
        mock_github_service.return_value.get_repositories.assert_called_once_with(
            workers=1, visibility="public", limit=1500
        )

    def test_collection_scope_is_forwarded_to_github_service(
        self,
        mock_owner_service: MagicMock,
        mock_asset_service: MagicMock,
        mock_github_service: MagicMock,
    ):
        owner = OwnerView(
            id=1,
            name="Test Owners",
            type="1",
            config=OwnerConfig(name="Test Owners", teams=[], prefix=None),
        )
        mock_owner_service.return_value.find_all.return_value = [owner]
        mock_owner_service.return_value.find_by_name.return_value = [owner]
        with (
            patch(
                "app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.collection_workers",
                3,
            ),
            patch(
                "app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.repository_visibility",
                "all",
            ),
            patch(
                "app.projects.repository_standards.jobs.map_github_repositories_to_owners.app_config.github.repository_limit",
                5000,
            ),
            self.app.app_context(),
        ):
            main()
        mock_github_service.return_value.get_repositories.assert_called_once_with(
            workers=3, visibility="all", limit=5000
        )

    def test_when_parent_team_has_admin_access_then_admin_relationship_created(
        self,
        mock_owner_service: MagicMock,
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

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict(), organisation="ministryofjustice")]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "ADMIN_ACCESS")]
        )

    def test_when_team_has_any_access_then_default_relationship_created(
        self,
        mock_owner_service: MagicMock,
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

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict(), organisation="ministryofjustice")]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )

    def test_when_parent_team_has_any_access_then_default_relationship_created(
        self,
        mock_owner_service: MagicMock,
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

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict(), organisation="ministryofjustice")]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )

    def test_when_prefix_matches_repository_name_then_default_relationship_created(
        self,
        mock_owner_service: MagicMock,
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

        with self.app.app_context():
            main()

        mock_owner_service.return_value.find_by_name.assert_has_calls(
            [call("Test Owners")]
        )
        mock_asset_service.return_value.update_asset_by_name.assert_has_calls(
            [call(mock_repository.basic.name, mock_repository.to_dict(), organisation="ministryofjustice")]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_has_calls(
            [call(mock_asset, mock_owner, "OTHER")]
        )

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
            [call(mock_repository.basic.name, mock_repository.to_dict(), organisation="ministryofjustice")]
        )
        mock_asset_service.return_value.update_relationships_with_owner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
