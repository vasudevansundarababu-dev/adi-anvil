from alembic import op

from anvil.config import ROOT

revision = "062"
down_revision = "061"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/062_benchmark_report_policy.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only report authorization history")
