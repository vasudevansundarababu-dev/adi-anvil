from alembic import op

from anvil.config import ROOT

revision = "058"
down_revision = "057"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/058_benchmark_deliverable_custody.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only exact deliverable and absence custody")
