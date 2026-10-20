"""Alembic environment: the deployment supplies its database URL explicitly."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from sentinel_replay.database import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.environ.get("SENTINEL_DATABASE_URL")
if not url:
    raise RuntimeError("SENTINEL_DATABASE_URL is required for migrations")


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
