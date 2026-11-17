from pathlib import Path

from alembic import op

revision = "083"
down_revision = "082"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/083_project_bindings.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Retain immutable Project binding and qualification history")
