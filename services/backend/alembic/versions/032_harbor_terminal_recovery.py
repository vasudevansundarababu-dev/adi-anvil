from alembic import op

revision = "032"
down_revision = "031"


def upgrade():
    # Minimal state-only visibility for idempotent terminal capture, never private data.
    op.execute("GRANT SELECT(state) ON anvil.harbor_checks TO anvil_worker")
    op.execute("INSERT INTO anvil.schema_versions(version) VALUES(32)")


def downgrade():
    raise RuntimeError("Use a forward migration; destructive downgrade is not authorized.")
