from alembic import op

from anvil.config import ROOT

revision = "018"
down_revision = "017"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/018_source_provenance.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; destructive downgrade is not authorized.")
