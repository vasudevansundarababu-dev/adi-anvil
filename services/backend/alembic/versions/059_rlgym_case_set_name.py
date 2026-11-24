from alembic import op

from anvil.config import ROOT

revision = "059"
down_revision = "058"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/059_rlgym_case_set_name.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 case set name")
