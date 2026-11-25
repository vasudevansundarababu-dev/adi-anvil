from alembic import op

from anvil.config import ROOT

revision = "064"
down_revision = "063"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/064_rlgym_policy_id_map.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 policy id map (D-056)")
