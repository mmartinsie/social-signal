"""Alembic environment: online migrations only, as the migrator role."""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

if context.is_offline_mode():
    raise SystemExit("Offline (SQL script) migrations are not supported.")

engine = create_engine(
    context.config.attributes["url"],
    poolclass=NullPool,
    # Never wait forever on a lock held by a running application: fail the
    # Job instead, which makes Helm abort the release before any rollout.
    connect_args={"options": "-c lock_timeout=10s -c statement_timeout=60s"},
)

with engine.connect() as connection:
    context.configure(connection=connection, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()
