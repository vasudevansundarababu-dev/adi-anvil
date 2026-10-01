from alembic import op

from anvil.config import ROOT

revision = "019"
down_revision = "018"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/019_evaluation_plans.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; destructive downgrade is not authorized.")
