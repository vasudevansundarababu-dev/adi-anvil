from pathlib import Path

from alembic import op

revision = "079"
down_revision = "078"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/079_praxis_generic_contract.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Template, qualification and protected resolution history are retained")
