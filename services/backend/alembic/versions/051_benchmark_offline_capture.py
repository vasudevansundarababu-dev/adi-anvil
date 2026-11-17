from alembic import op

from anvil.config import ROOT

revision = "051"
down_revision = "050"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/051_benchmark_offline_capture.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only immutable native capture metadata")
