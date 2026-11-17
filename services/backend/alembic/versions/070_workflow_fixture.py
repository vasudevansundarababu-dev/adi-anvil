"""Zero-cost workflow conformance persistence; native graph admission stays closed."""

from pathlib import Path

from alembic import op

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/070_workflow_fixture.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Workflow effect history cannot be destructively downgraded")
