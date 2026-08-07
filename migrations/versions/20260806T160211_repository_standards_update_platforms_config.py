from alembic import op


# revision identifiers, used by Alembic.
revision = "64b771c789c0"
down_revision = "5ecaf0b9197d"


def upgrade():
    op.execute(
        """
        UPDATE owners
        SET name = 'Office of the CTO', config ='{"name":"Office of the CTO", "teams":["office-of-the-cto", "platforms","hosting-migrations","aws-root-account-admin-team","webops","studio-webops","analytical-platform","data-engineering","analytics-hq","data-catalogue","data-platform","data-and-analytics-engineering","observability-platform"], "prefix":""}'::jsonb
        WHERE name = 'Platforms'
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE owners
        SET name = 'Platforms', config ='{"name":"Platforms", "teams":["platforms","hosting-migrations","aws-root-account-admin-team","webops","studio-webops","analytical-platform","data-engineering","analytics-hq","data-catalogue","data-platform","data-and-analytics-engineering","observability-platform"], "prefix":""}'::jsonb
        WHERE name = 'Office of the CTO'
        """
    )
