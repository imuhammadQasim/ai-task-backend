# app/database.py
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# asyncpg doesn't accept libpq-style query params like sslmode/channel_binding
# (used by Neon's connection string); strip them and request SSL via connect_args.
_url_parts = urlsplit(settings.DATABASE_URL)
_query = dict(parse_qsl(_url_parts.query))
_query.pop("sslmode", None)
_query.pop("channel_binding", None)
_async_db_url = urlunsplit(_url_parts._replace(query=urlencode(_query)))

engine = create_async_engine(
    _async_db_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"ssl": "require"},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()