from alembic import op

from anvil.config import ROOT

revision = "069"
down_revision = "068"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/069_rlgym_test_only.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 test-only projects")
