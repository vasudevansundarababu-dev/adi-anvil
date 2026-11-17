from pathlib import Path

from alembic import op

revision = "080"
down_revision = "079"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/080_golden_paid_calls.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Paid request claims and unknown-cost reservations must be retained")
