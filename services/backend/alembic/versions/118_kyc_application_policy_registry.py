from pathlib import Path

from alembic import op

revision = "118"
down_revision = "117"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/118_kyc_application_policy_registry.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable KYC qualification and revocation history")
