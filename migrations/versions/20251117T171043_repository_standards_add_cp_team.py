from alembic import op


# revision identifiers, used by Alembic.
revision = "e4f83d567c20"
down_revision = "dd9bb95208a8"


def upgrade():
    op.execute(
        """
        INSERT INTO owners (name, type_id) VALUES
        ('Cloud Platform', 2)
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM owners WHERE name = 'Cloud Platform';
        """
    )
