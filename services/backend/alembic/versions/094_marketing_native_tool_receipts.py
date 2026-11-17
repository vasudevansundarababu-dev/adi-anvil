from pathlib import Path

from alembic import op

revision = "094"
down_revision = "093"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2]
            / "migrations/094_marketing_native_tool_receipts.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve role-scoped Marketing effect receipts")
