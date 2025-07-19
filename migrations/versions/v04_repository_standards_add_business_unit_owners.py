from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "v04"
down_revision = "v03"
branch_labels = None
depends_on = None

OWNERS = [
    "Central Digital",
    "CICA",
    "HMPPS",
    "LAA",
    "OPG",
    "Platforms",
    "Technology Services",
]


def upgrade():
    owners = sa.Table(
        "owners",
        sa.MetaData(),
        sa.Column("name", sa.String(), nullable=False),
    )

    op.bulk_insert(owners, [{"name": name} for name in OWNERS])


def downgrade():
    owners = sa.Table(
        "owners",
        sa.MetaData(),
        sa.Column("name", sa.String(), nullable=False),
    )

    op.execute(owners.delete().where(owners.c.name.in_(OWNERS)))
