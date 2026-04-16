from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5ecaf0b9197d"
down_revision = "e4f83d567c20"


def upgrade():
    op.add_column(
        "owners",
        sa.Column("config", sa.JSON()),
    )

    op.execute(
        """
        UPDATE owners
        SET config = CASE name
            WHEN 'HMPPS' THEN '{"name":"HMPPS", "teams":["hmpps-developers"], "prefix":"hmpps-"}'::jsonb
            WHEN 'LAA' THEN '{"name":"LAA", "teams":["laa-admins","laa-technical-architects","laa-developers","laa-crime-apps-team","laa-crime-apply","laa-eligibility-platform","laa get access","laa payments and billing","payforlegalaid"], "prefix":"laa-"}'::jsonb
            WHEN 'OPG' THEN '{"name":"OPG", "teams":["opg"], "prefix":"opg-"}'::jsonb
            WHEN 'CICA' THEN '{"name":"CICA", "teams":["cica"], "prefix":"cica-"}'::jsonb
            WHEN 'Central Digital' THEN '{"name":"central digital", "teams":["central-digital-product-team","tactical-products","form-builder","hale-platform","jotw-content-devs","mojds-maintainers","mojds-admins"], "prefix":"bichard7"}'::jsonb
            WHEN 'Platforms' THEN '{"name":"Platforms", "teams":["platforms","hosting-migrations","aws-root-account-admin-team","webops","studio-webops","analytical-platform","data-engineering","analytics-hq","data-catalogue","data-platform","data-and-analytics-engineering","observability-platform"], "prefix":""}'::jsonb
            WHEN 'Technology Services' THEN '{"name":"Technology Services", "teams":["nvvs-devops-admins","moj-official-techops","cloud-ops-alz-admins","technology-services"], "prefix":""}'::jsonb
            WHEN 'Modernisation Platform' THEN '{"name":"Modernisation Platform", "teams":["modernisation-platform"], "prefix":""}'::jsonb
            WHEN 'GitHub Community' THEN '{"name":"GitHub Community", "teams":["github-community"], "prefix":""}'::jsonb
            WHEN 'Cloud Platform' THEN '{"name":"Cloud Platform", "teams":["webops"], "prefix":""}'::jsonb
        END
        WHERE name in ('HMPPS', 'LAA', 'OPG','CICA','Central Digital','Platforms','Technology Services','Modernisation Platform','GitHub Community','Cloud Platform')
        """
    )

    op.execute(
        """
        INSERT INTO owners (name, type_id, config) VALUES
        ('HMCTS', 1, '{"name":"HMCTS", "teams":["sustainingdevs"], "prefix":""}'::jsonb)
        """
    )


def downgrade():
    op.drop_column("owners", "config")
    op.execute(
        """
        DELETE FROM owners WHERE name = 'HMCTS';
        """
    )
