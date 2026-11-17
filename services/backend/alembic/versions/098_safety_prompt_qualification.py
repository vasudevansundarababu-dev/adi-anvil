from pathlib import Path

from alembic import op

revision = "098"
down_revision = "097"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/098_safety_prompt_qualification.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve exact safety prompt review and revocation custody")
