from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "v02"
down_revision = "v01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "acronyms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("abbreviation", sa.String(), nullable=False),
        sa.Column("definition", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "abbreviation", "definition", name="_abbreviation_definition_uc"
        ),
    )


def downgrade():
    op.drop_table("acronyms")
