from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "v01"
down_revision = None
branch_labels = None
depends_on = None


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


def downgrade():
    op.drop_table("relationships")
    op.drop_table("owners")
    op.drop_table("assets")
