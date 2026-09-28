from alembic import op

from anvil.config import ROOT

revision = "003"
down_revision = "002"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/003_imports.sql").read_text()
    )


def downgrade():
    raise RuntimeError("Destructive downgrade is not authorized; use a forward migration.")
