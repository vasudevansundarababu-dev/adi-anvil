from alembic import op

from anvil.config import ROOT

revision = "060"
down_revision = "059"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/060_benchmark_dashboard_trace_audit.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only immutable historical audit")
