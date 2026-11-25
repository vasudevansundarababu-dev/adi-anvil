from alembic import op

from anvil.config import ROOT

revision = "067"
down_revision = "066"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/067_rlgym_lookup_runs.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 lookup baseline runs (G4)")
