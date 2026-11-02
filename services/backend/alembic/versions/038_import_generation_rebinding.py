from alembic import op

from anvil.config import ROOT

revision = "038"
down_revision = "037"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/038_import_generation_rebinding.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only import configuration bindings")
