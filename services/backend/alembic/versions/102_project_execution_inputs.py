from pathlib import Path

from alembic import op

revision = "102"
down_revision = "101"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/102_project_execution_inputs.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable execution inputs and sampling provenance")
