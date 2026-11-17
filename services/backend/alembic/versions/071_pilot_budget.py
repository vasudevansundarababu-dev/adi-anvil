"""Retained pilot envelopes; no policy or paid activation seed."""

from pathlib import Path

from alembic import op

revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/071_pilot_budget.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Pilot reservations must be retained")
