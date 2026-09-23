from alembic import context
from app.storage import Base

with context.config.attributes["connection"] as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
