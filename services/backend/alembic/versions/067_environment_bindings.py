from alembic import op

from anvil.config import ROOT

revision = "067"
down_revision = "066"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/067_environment_bindings.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only frozen task bindings and evaluations")
