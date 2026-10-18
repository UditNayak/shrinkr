import logging

from alembic import context

from app import models  # noqa: F401  (importing registers the tables on Base.metadata)
from app.db import Base, engine

# Show "Running upgrade ..." lines when run from the command line.
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

with engine.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        # SQLite can't ALTER most things in place; batch mode rebuilds the table instead.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()
