from pathlib import Path

from alembic import op

revision = "099"
down_revision = "098"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/099_campaign_private_grading.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve campaign private references, grades and custody")
