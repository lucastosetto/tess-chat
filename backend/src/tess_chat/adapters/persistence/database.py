import ssl

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str, require_ssl: bool) -> AsyncEngine:
    connect_args: dict[str, object] = {}
    if require_ssl:
        connect_args["ssl"] = ssl.create_default_context()
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        connect_args=connect_args,
    )


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
