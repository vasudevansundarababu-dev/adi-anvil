from alembic import op

from anvil.config import ROOT

revision = "020"
down_revision = "019"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/020_praxis_harbor.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; destructive downgrade is not authorized.")
