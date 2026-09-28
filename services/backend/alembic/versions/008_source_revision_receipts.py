from alembic import op

from anvil.config import ROOT

revision = "008"
down_revision = "007"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/008_source_revision_receipts.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Destructive downgrade is not authorized; use a forward migration.")
