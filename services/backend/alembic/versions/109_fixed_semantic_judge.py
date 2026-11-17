from pathlib import Path

from alembic import op

revision = "109"
down_revision = "108"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/109_fixed_semantic_judge.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve independently frozen judge and candidate evidence")
