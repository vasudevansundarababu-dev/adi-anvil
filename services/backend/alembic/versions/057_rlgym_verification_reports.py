from alembic import op

from anvil.config import ROOT

revision = "057"
down_revision = "056"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/057_rlgym_verification_reports.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 verification reports")
