from alembic import op

from anvil.config import ROOT

revision = "050"
down_revision = "049"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/050_benchmark_offline_runtime.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only immutable offline execution evidence")
