from pathlib import Path

from alembic import op

revision = "077"
down_revision = "076"


def upgrade():
    op.execute(
        (
            Path(__file__).resolve().parents[2] / "migrations/077_dataset_export_receipts.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Dataset export provenance and resolution history are retained")
