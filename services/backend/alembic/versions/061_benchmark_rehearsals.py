from alembic import op

from anvil.config import ROOT

revision = "061"
down_revision = "060"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/061_benchmark_rehearsals.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only immutable software rehearsal evidence")
