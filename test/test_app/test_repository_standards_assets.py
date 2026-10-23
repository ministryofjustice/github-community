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


class TestOrganisationMigration(unittest.TestCase):
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