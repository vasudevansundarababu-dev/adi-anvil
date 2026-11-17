from alembic import op

from anvil.config import ROOT

revision = "049"
down_revision = "048"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/049_benchmark_evaluation_revocation.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only evaluator custody and immutable reports")
