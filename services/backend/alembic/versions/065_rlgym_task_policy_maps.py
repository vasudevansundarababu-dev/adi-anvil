from alembic import op

from anvil.config import ROOT

revision = "065"
down_revision = "064"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/065_rlgym_task_policy_maps.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 task policy maps (D-056)")
