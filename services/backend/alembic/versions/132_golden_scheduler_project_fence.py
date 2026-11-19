from pathlib import Path

from alembic import op

revision = "132"
down_revision = "131"


def upgrade():
    c = op.get_bind()
    if c.exec_driver_sql("SELECT 1 FROM anvil.schema_versions WHERE version=132").first() is None:
        c.exec_driver_sql((Path(__file__).resolve().parents[2] / "migrations/132_golden_scheduler_project_fence.sql").read_text(),
                          execution_options={"no_parameters": True})


def downgrade():
    raise RuntimeError("Destructive downgrade is not authorized; use a forward migration.")
