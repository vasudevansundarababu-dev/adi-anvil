from alembic import op

from anvil.config import ROOT

revision = "054"
down_revision = "053"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/054_rlgym_clause_outcomes.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 clause outcomes")
