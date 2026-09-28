from sqlalchemy import create_engine

from alembic import context
from anvil.config import setting

engine = create_engine(
    setting("MIGRATION_DATABASE_URL").replace("postgresql://", "postgresql+psycopg://", 1)
)
with engine.connect() as connection:
    context.configure(connection=connection, version_table_schema="anvil", transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()
