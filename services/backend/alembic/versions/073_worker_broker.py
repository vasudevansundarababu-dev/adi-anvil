"""API-mediated pilot dispatch; preserve worker private-data isolation."""

from pathlib import Path

from alembic import op

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/073_worker_broker.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Do not restore worker receipt mutation privileges")
