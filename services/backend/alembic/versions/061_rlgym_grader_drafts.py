from alembic import op

from anvil.config import ROOT

revision = "061"
down_revision = "060"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/061_rlgym_grader_drafts.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 grader drafts")
