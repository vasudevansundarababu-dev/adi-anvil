from alembic import op

from anvil.config import ROOT

revision = "065"
down_revision = "064"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/065_benchmark_runs.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only benchmark Run evidence")
