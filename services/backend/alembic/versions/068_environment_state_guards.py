from alembic import op

from anvil.config import ROOT

revision = "068"
down_revision = "067"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/068_environment_state_guards.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only environment state integrity")
