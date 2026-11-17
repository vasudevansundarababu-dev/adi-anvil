from pathlib import Path

from alembic import op

revision = "088"
down_revision = "087"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/088_shared_execution_budgets.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve retained shared spending reservations")
