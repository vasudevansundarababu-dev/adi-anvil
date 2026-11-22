from alembic import op

from anvil.config import ROOT

revision = "043"
down_revision = "042"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/043_rlgym_results.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 results")
