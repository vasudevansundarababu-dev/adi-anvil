from pathlib import Path

from alembic import op

revision = "081"
down_revision = "080"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/081_praxis_workload_identity.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Service-principal grants and revocation evidence must be retained")
