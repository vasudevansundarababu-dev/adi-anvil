"""Durable parallel workflow and authenticated human waits; no native enable."""

from pathlib import Path

from alembic import op

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/072_workflow_runtime.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Workflow and human history must be retained")
