from alembic import op

from anvil.config import ROOT

revision = "029"
down_revision = "028"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/029_workspace_preparations.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; destructive downgrade is not authorized.")
