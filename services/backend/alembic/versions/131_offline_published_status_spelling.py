from pathlib import Path

from alembic import op

revision = "131"
down_revision = "130"


def upgrade():
    c = op.get_bind()
    if c.exec_driver_sql("SELECT 1 FROM anvil.schema_versions WHERE version=131").first() is None:
        c.exec_driver_sql((Path(__file__).resolve().parents[2] / "migrations/131_offline_published_status_spelling.sql").read_text(),
                          execution_options={"no_parameters": True})


def downgrade():
    raise RuntimeError("Destructive downgrade is not authorized; use a forward migration.")
