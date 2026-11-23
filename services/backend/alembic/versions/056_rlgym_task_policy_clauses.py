from alembic import op

from anvil.config import ROOT

revision = "056"
down_revision = "055"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/056_rlgym_task_policy_clauses.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 task policy clauses")
