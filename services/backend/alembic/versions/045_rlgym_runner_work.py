from alembic import op

from anvil.config import ROOT

revision = "045"
down_revision = "044"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/045_rlgym_runner_work.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 runner work lookup")
