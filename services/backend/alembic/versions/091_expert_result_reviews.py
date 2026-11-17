from pathlib import Path

from alembic import op

revision = "091"
down_revision = "090"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/091_expert_result_reviews.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve expert assessment, diagnosis and report history")
