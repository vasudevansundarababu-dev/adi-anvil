"""Bind Golden KYC into canonical Anvil registries and execution/report records."""

from pathlib import Path

from alembic import op

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/076_golden_kyc_anvil.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Golden Anvil bindings and execution history are retained")
