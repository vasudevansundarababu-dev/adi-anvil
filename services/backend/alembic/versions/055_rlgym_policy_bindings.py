from alembic import op

from anvil.config import ROOT

revision = "055"
down_revision = "054"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/055_rlgym_policy_bindings.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 policy bindings")
