from pathlib import Path

from alembic import op

revision = "116"
down_revision = "115"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/116_marketing_api_evidence.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable API evidence custody")
