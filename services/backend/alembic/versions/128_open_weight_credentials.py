from pathlib import Path

from alembic import op

revision = "128"
down_revision = "127"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/128_open_weight_credentials.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable Hugging Face credential bindings")
