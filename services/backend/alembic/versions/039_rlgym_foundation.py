from alembic import op

from anvil.config import ROOT

revision = "039"
down_revision = "038"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/039_rlgym_foundation.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 foundation")
