from pathlib import Path

from alembic import op

revision = "085"
down_revision = "084"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/085_praxis_project_intakes.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable authored-package intake provenance")
