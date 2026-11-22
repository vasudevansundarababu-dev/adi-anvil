from alembic import op

from anvil.config import ROOT

revision = "046"
down_revision = "045"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/046_rlgym_registry_source.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 registry source")
