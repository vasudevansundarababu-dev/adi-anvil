from alembic import op

from anvil.config import ROOT

revision = "043"
down_revision = "042"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/043_benchmark_import_summaries.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only benchmark import summaries")
