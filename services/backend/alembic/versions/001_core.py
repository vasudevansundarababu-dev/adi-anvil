from alembic import op
from anvil.config import ROOT

revision = "001"
down_revision = None


def upgrade():
    c = op.get_bind()
    if c.exec_driver_sql("SELECT to_regclass('anvil.schema_versions')").scalar() is None:
        c.exec_driver_sql((ROOT / "services/backend/migrations/001_core.sql").read_text())


def downgrade():
    raise RuntimeError(
        "Destructive downgrade is not authorized; restore into a disposable target or forward-fix."
    )
