from pathlib import Path

from alembic import op

revision = "136"
down_revision = "135"


def upgrade():
    connection = op.get_bind()
    if connection.exec_driver_sql("SELECT 1 FROM anvil.schema_versions WHERE version=136").first() is None:
        connection.exec_driver_sql(
            (Path(__file__).resolve().parents[2] / "migrations/136_task_method_operator.sql").read_text(),
            execution_options={"no_parameters": True},
        )


def downgrade():
    raise RuntimeError("Destructive downgrade is not authorized; use a forward migration.")
