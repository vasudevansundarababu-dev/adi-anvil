from alembic import op

from anvil.config import ROOT

revision = "047"
down_revision = "046"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/047_benchmark_evaluation.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only evaluator custody and immutable reports")
