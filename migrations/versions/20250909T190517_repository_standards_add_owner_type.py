from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "47de5f7d0f0e"
down_revision = "d69ddc74df68"


def upgrade():
    op.add_column(
        "owners",
        sa.Column("type_id", sa.Integer(), nullable=True),
    )
    op.create_table(
        "owner_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(
        "fk_owners_type_id_owner_types",
        "owners",
        "owner_types",
        ["type_id"],
        ["id"],
    )
    op.bulk_insert(
        sa.table(
            "owner_types",
            sa.column("id", sa.Integer),
            sa.column("name", sa.String),
        ),
        [
            {"id": 1, "name": "BUSINESS_UNIT"},
            {"id": 2, "name": "TEAM"},
        ],
    )
    op.execute("UPDATE owners SET type_id = 1")
    op.execute(
        """
        INSERT INTO owners (name, type_id) VALUES
        ('Modernisation Platform', 2),
        ('GitHub Community', 2)
        """
    )


def downgrade():
    op.drop_table("owner_types")
    op.drop_column("owners", "type_id")
