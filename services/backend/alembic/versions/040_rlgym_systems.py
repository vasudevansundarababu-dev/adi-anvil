from alembic import op

from anvil.config import ROOT

revision = "040"
down_revision = "039"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/040_rlgym_systems.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 systems")
