from pathlib import Path

from alembic import op

revision = "123"
down_revision = "122"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/123_marketing_private_result_custody.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve actual original private grade/result custody")
