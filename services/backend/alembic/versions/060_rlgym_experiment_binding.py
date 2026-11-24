from alembic import op

from anvil.config import ROOT

revision = "060"
down_revision = "059"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/060_rlgym_experiment_binding.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 experiment binding")
