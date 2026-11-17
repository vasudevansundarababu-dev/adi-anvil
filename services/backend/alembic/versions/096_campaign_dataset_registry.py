from pathlib import Path

from alembic import op

revision = "096"
down_revision = "095"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/096_campaign_dataset_registry.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable campaign case packs and qualification custody")
