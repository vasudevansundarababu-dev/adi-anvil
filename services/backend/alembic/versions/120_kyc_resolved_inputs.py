from pathlib import Path

from alembic import op

revision = "120"
down_revision = "119"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/120_kyc_resolved_inputs.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable original KYC input bindings")
