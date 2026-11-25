from alembic import op

from anvil.config import ROOT

revision = "063"
down_revision = "062"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/063_rlgym_provider_refused.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 provider-refused episodes (D-054)")
