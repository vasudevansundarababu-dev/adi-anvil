from alembic import op

from anvil.config import ROOT

revision = "041"
down_revision = "040"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/041_benchmark_canonical_bindings.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only canonical benchmark evidence")
