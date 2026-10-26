import unittest
from datetime import datetime, timedelta
from importlib import import_module
from unittest.mock import patch

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

from app.projects.repository_standards.db_models import Asset, Owner, OwnerTypes, Relationship, db
from app.projects.repository_standards.repositories.asset_repository import AssetRepository
from app.projects.repository_standards.repositories.owner_repository import OwnerRepository
from app.projects.repository_standards.models.owner import OwnerConfig
from app.projects.repository_standards.services.asset_service import AssetService


class TestOrganisationAssetIdentity(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.addCleanup(db.session.remove)
        db.create_all()
        self.repository = AssetRepository()
        self.service = AssetService(self.repository)

    def test_repository_visibility_filter_runs_in_database_and_lists_all_orgs(self):
        self.repository.add_asset(
            "public-moj", "REPOSITORY", {"basic": {"visibility": "public"}}
        )
        self.repository.add_asset(
            "private-mojas", "REPOSITORY",
            {"basic": {"visibility": "private"}},
            "moj-analytical-services",
        )
        with patch(
            "app.projects.repository_standards.repositories.asset_repository.RepositoryView.from_asset",
            side_effect=lambda asset: asset.name,
        ):
            self.assertEqual(
                self.repository.find_all(visibility="public"), ["public-moj"]
            )
        self.assertEqual(
            self.repository.find_all_organisations(),
            ["ministryofjustice", "moj-analytical-services"],
        )

    def test_duplicate_names_are_updated_and_looked_up_independently(self):
        moj = self.service.update_asset_by_name("shared", {"version": 1})
        mojas = self.service.update_asset_by_name(
            "shared", {"version": 2}, "moj-analytical-services"
        )
        self.assertNotEqual(moj.id, mojas.id)
        self.service.update_asset_by_name(
            "shared", {"version": 3}, "moj-analytical-services"
        )
        self.assertEqual(self.repository.find_by_name("shared"), [moj])
        self.assertEqual(
            self.repository.find_by_name("shared", "moj-analytical-services"), [mojas]
        )
        self.assertEqual(moj.data, {"version": 1})
        self.assertEqual(mojas.data, {"version": 3})

    def test_cleanup_leaves_other_organisations_and_empty_scopes_untouched(self):
        moj = self.repository.add_asset("old", "REPOSITORY", {})
        mojas = self.repository.add_asset(
            "old", "REPOSITORY", {}, "moj-analytical-services"
        )
        moj.last_updated = mojas.last_updated = datetime.now() - timedelta(days=2)
        db.session.commit()
        self.service.remove_stale_assets([])
        self.assertEqual(db.session.query(Asset).count(), 2)
        self.service.remove_stale_assets(["ministryofjustice"])
        self.assertEqual(db.session.query(Asset).all(), [mojas])

    def test_relationship_cleanup_only_removes_scanned_org_relationships(self):
        owner_type = OwnerTypes(name="TEAM")
        owner = Owner(name="team", type=owner_type, config={})
        db.session.add(owner)
        db.session.commit()
        relationships = []
        for organisation in ("ministryofjustice", "moj-analytical-services"):
            asset = self.repository.add_asset("shared", "REPOSITORY", {}, organisation)
            relationship = Relationship(
                owner=owner,
                asset=asset,
                type="OTHER",
                last_updated=datetime.now() - timedelta(days=2),
            )
            db.session.add(relationship)
            relationships.append(relationship)
        db.session.commit()
        self.service.remove_stale_relationships(["ministryofjustice"])
        self.assertEqual(db.session.query(Relationship).all(), [relationships[1]])
        self.assertEqual(db.session.query(Asset).count(), 2)

    def test_owner_update_preserves_configured_organisation_and_prefix(self):
        owner_type = OwnerTypes(name="TEAM")
        owner = Owner(
            name="Analytics Team",
            type=owner_type,
            config=OwnerConfig(
                name="Analytics Team",
                teams=["old-team"],
                prefix="analytics-",
                organisation="moj-analytical-services",
            ).to_dict(),
        )
        db.session.add(owner)
        db.session.commit()

        updated = OwnerRepository().update_by_id(
            str(owner.id), "Renamed Analytics Team", ["new-team"]
        )

        config = OwnerConfig.from_dict(updated.config)
        self.assertEqual(config.organisation, "moj-analytical-services")
        self.assertEqual(config.prefix, "analytics-")
        self.assertEqual(config.teams, ["new-team"])


class TestOrganisationMigration(unittest.TestCase):
    def test_flow_dataset_downgrade_preserves_existing_boards_and_observations(self):
        migration = import_module(
            "migrations.versions.20261019T180000_flow_datasets"
        )
        engine = sa.create_engine("sqlite://")
        metadata = sa.MetaData()
        boards = sa.Table(
            "flow_metrics_boards",
            metadata,
            sa.Column("id", sa.String, primary_key=True),
        )
        runs = sa.Table(
            "flow_metrics_runs",
            metadata,
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("board_id", sa.String, sa.ForeignKey("flow_metrics_boards.id")),
        )
        snapshots = sa.Table(
            "flow_metrics_snapshots",
            metadata,
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("board_id", sa.String, sa.ForeignKey("flow_metrics_boards.id")),
        )
        datasets = sa.Table(
            "flow_metrics_datasets", metadata, sa.Column("id", sa.String, primary_key=True)
        )
        evidence = sa.Table(
            "flow_metrics_evidence", metadata, sa.Column("id", sa.String, primary_key=True)
        )

        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(boards.insert().values(id="sample-three-sprints"))
            connection.execute(runs.insert().values(id="run-1", board_id="sample-three-sprints"))
            connection.execute(snapshots.insert().values(id="snapshot-1", board_id="sample-three-sprints"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
            self.assertEqual(connection.execute(sa.select(boards.c.id)).scalars().all(), ["sample-three-sprints"])
            self.assertEqual(connection.execute(sa.select(runs.c.id)).scalars().all(), ["run-1"])
            self.assertEqual(connection.execute(sa.select(snapshots.c.id)).scalars().all(), ["snapshot-1"])
            self.assertNotIn("flow_metrics_datasets", sa.inspect(connection).get_table_names())
            self.assertNotIn("flow_metrics_evidence", sa.inspect(connection).get_table_names())
        engine.dispose()

    def test_existing_rows_are_backfilled_and_legacy_inserts_keep_working(self):
        migration = import_module(
            "migrations.versions.20261022T120000_repository_standards_add_asset_organisation"
        )
        engine = sa.create_engine("sqlite://")
        with engine.begin() as connection:
            assets = sa.Table(
                "assets", sa.MetaData(),
                sa.Column("id", sa.Integer, primary_key=True),
                sa.Column("name", sa.String),
            )
            assets.create(connection)
            connection.execute(assets.insert().values(name="existing"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            migrated = sa.Table("assets", sa.MetaData(), autoload_with=connection)
            connection.execute(migrated.insert().values(name="legacy-insert"))
            self.assertEqual(
                connection.execute(sa.select(migrated.c.organisation)).scalars().all(),
                ["ministryofjustice", "ministryofjustice"],
            )
            self.assertIn(
                "ix_assets_organisation_name",
                {index["name"] for index in sa.inspect(connection).get_indexes("assets")},
            )
        engine.dispose()