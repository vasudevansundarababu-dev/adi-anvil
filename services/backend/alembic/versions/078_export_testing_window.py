from pathlib import Path

from alembic import op

revision = "078"
down_revision = "077"


def upgrade():
    op.execute(
        (
            Path(__file__).resolve().parents[2] / "migrations/078_export_testing_window.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Export credential and revocation history is retained")
