from alembic import op

from anvil.config import ROOT

revision = "044"
down_revision = "043"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/044_rlgym_sme.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 SME review")
