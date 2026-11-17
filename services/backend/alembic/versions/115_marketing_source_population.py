from pathlib import Path

from alembic import op

revision = "115"
down_revision = "114"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/115_marketing_source_population.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve source-complete opening world evidence")
