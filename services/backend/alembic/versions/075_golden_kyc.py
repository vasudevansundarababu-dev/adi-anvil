"""Add isolated Golden KYC pilot schemas."""

from pathlib import Path

from alembic import op

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/075_golden_kyc.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError(
        "Golden KYC audit is retained; rollback disables routes, never deletes history"
    )
