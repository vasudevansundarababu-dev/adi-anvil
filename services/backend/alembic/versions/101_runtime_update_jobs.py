from pathlib import Path

from alembic import op

revision = "101"
down_revision = "100"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/101_runtime_update_jobs.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve pinned runtime update attempts and physical custody")
