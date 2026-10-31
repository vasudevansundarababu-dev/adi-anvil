from alembic import op

from anvil.config import ROOT

revision = "022"
down_revision = "021"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/022_harbor_fencing.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; destructive downgrade is not authorized.")
