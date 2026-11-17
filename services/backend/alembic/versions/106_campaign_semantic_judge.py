from pathlib import Path

from alembic import op

revision = "106"
down_revision = "105"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/106_campaign_semantic_judge.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve native grading authority and private judge custody")
