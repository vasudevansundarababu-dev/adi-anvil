from alembic import op

from anvil.config import ROOT

revision = "035"
down_revision = "034"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/035_workspace_trials.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; task environments and run trials are immutable.")
