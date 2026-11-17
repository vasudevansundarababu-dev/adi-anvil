from pathlib import Path

from alembic import op

revision = "127"
down_revision = "126"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/127_kyc_application_policy_materializations.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve exact qualified policy delivery provenance")
