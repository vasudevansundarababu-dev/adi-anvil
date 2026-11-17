from pathlib import Path

from alembic import op

revision = "107"
down_revision = "106"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/107_marketing_response_protocol.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable completed-response failure custody")
