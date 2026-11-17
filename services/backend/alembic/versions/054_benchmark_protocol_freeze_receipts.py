from alembic import op

from anvil.config import ROOT

revision = "054"
down_revision = "053"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            ROOT / "services/backend/migrations/054_benchmark_protocol_freeze_receipts.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only canonical benchmark freeze receipts")
