from alembic import op

from anvil.config import ROOT

revision = "048"
down_revision = "047"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/048_benchmark_sealed_custody.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only evaluator custody and immutable reports")
