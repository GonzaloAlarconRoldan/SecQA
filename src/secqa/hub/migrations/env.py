"""Alembic environment. Works both from `alembic` CLI (dev autogenerate) and from
`secqa.hub.db.upgrade_schema`, which passes an open connection via config attributes."""
from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from secqa.hub.config import get_settings
from secqa.hub.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(get_settings().resolved_database_url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
