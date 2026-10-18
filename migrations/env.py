import logging

from alembic import context

from app import models  # noqa: F401
from app.db import Base, engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

with engine.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()
