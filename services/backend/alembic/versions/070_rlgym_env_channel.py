from alembic import op

from anvil.config import ROOT

revision = "070"
down_revision = "069"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/070_rlgym_env_channel.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 environment version channel")
