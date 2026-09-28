from alembic import op

from anvil.config import ROOT

revision = "002"
down_revision = "001"


def upgrade():
    c = op.get_bind()
    if c.exec_driver_sql("SELECT 1 FROM anvil.schema_versions WHERE version=2").first() is None:
        c.exec_driver_sql(
            (ROOT / "services/backend/migrations/002_provider_gates.sql").read_text(),
            execution_options={"no_parameters": True},
        )


def downgrade():
    raise RuntimeError("Destructive downgrade is not authorized; use a forward migration.")
