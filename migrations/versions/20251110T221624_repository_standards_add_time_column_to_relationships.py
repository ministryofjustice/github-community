from datetime import datetime
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "dd9bb95208a8"
down_revision = "47de5f7d0f0e"


def upgrade():
    op.add_column(
        "relationships",
        sa.Column(
            "last_updated", sa.DateTime(), nullable=True, default=datetime.utcnow()
        ),
    )


def downgrade():
    op.drop_column("relationships", "type_id")
