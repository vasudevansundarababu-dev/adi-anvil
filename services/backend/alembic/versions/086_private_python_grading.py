from pathlib import Path

from alembic import op

revision = "086"
down_revision = "085"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/086_private_python_grading.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve private scoring receipts and immutable input custody")
