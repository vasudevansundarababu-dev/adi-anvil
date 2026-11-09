from alembic import op

from anvil.config import ROOT

revision = "066"
down_revision = "065"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/066_environment_factory.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only environment and evidence history")
