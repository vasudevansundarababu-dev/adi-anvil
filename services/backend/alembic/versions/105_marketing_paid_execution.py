from pathlib import Path

from alembic import op

revision = "105"
down_revision = "104"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/105_marketing_paid_execution.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve Marketing role/source, one-shot action and spending custody")
