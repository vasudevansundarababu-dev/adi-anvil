from alembic import op

from anvil.config import ROOT

revision = "057"
down_revision = "056"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/057_benchmark_public_source_metadata.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only original source metadata")
