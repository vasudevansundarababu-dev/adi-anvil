"""Durable environment build jobs and benchmark attempts."""

from pathlib import Path
from alembic import op

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/069_environment_execution.sql"
        ).read_text()
    )


def downgrade():
    raise RuntimeError("Append-only execution history cannot be destructively downgraded")
