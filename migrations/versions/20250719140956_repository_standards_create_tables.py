import sqlalchemy as sa
from alembic import op
from sqlalchemy import Integer, String
from sqlalchemy.sql import column, table

# revision identifiers, used by Alembic.
revision = "0e13a38dec3d"
down_revision = None


def upgrade():
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("last_updated", sa.DateTime(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "owners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "relationships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("assets_id", sa.Integer(), nullable=False),
        sa.Column("owners_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assets_id"],
            ["assets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["owners_id"],
            ["owners.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    owners_table = table(
        "owners",
        column("id", Integer),
        column("name", String),
    )

    op.bulk_insert(
        owners_table,
        [
            {"name": name}
            for name in [
                "Central Digital",
                "CICA",
                "HMPPS",
                "LAA",
                "OPG",
                "Platforms",
                "Technology Services",
            ]
        ],
    )


def downgrade():
    op.drop_table("relationships")
    op.drop_table("owners")
    op.drop_table("assets")
