from alembic import op

from anvil.config import ROOT

revision = "055"
down_revision = "054"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/055_benchmark_offline_reconciliation.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only immutable operator reconciliation")
