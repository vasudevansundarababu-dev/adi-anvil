from pathlib import Path

from alembic import op

revision = "097"
down_revision = "096"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/097_runtime_admin.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve runtime observation and candidate history")
