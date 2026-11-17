from pathlib import Path

from alembic import op

revision = "103"
down_revision = "102"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/103_runtime_qa_operator.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve runtime admissions, invalidations and post-cutover evidence")
