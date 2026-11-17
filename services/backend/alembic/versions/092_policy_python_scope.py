from pathlib import Path

from alembic import op

revision = "092"
down_revision = "091"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/092_policy_python_scope.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve scoped policy grading evidence")
