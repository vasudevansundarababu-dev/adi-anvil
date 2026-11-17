from alembic import op

from anvil.config import ROOT

revision = "056"
down_revision = "055"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/056_benchmark_native_operator_role.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only native evaluator operator role guard")
