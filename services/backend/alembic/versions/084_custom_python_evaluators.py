from pathlib import Path

from alembic import op

revision = "084"
down_revision = "083"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/084_custom_python_evaluators.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Retain immutable custom Python programs, attempts and results")
