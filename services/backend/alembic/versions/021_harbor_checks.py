from alembic import op

from anvil.config import ROOT

revision = "021"
down_revision = "020"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/021_harbor_checks.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; destructive downgrade is not authorized.")
