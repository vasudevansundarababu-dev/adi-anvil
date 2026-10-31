from alembic import op

from anvil.config import ROOT

revision = "028"
down_revision = "027"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/028_workspace_profile_mapping.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; destructive downgrade is not authorized.")
