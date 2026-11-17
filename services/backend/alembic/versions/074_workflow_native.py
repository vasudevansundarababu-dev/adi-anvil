"""Exact source-bound graph execution and human wake-up; no enable or source seeds."""

from pathlib import Path

from alembic import op

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/074_workflow_native.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Native workflow histories must be retained")
