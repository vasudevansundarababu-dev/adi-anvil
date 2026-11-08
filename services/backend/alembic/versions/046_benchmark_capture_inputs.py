from alembic import op

from anvil.config import ROOT

revision = "046"
down_revision = "045"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/046_benchmark_capture_inputs.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only immutable qualification bindings")
