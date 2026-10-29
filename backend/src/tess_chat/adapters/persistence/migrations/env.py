import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from tess_chat.adapters.persistence.database import create_engine
from tess_chat.adapters.persistence.models import Base
from tess_chat.config import Settings

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    settings = Settings()
    engine = create_engine(settings.async_database_url, settings.database_requires_ssl)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


asyncio.run(_main())
