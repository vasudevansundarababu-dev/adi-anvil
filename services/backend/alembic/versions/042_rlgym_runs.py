from alembic import op

from anvil.config import ROOT

revision = "042"
down_revision = "041"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/042_rlgym_runs.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 runs")
