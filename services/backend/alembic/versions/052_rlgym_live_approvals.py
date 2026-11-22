from alembic import op

from anvil.config import ROOT

revision = "052"
down_revision = "051"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/052_rlgym_live_approvals.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 live approvals")
