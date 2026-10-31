from alembic import op

from anvil.config import ROOT

revision = "030"
down_revision = "029"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/030_workspace_model_versions.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; destructive downgrade is not authorized.")
