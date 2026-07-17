from collections.abc import AsyncGenerator

from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from api.common.db.engine import AsyncEngine, AsyncSession, AsyncSessionMaker, Engine
from api.common.db.engine import create_async_engine as _create_async_engine
from api.common.db.engine import create_sync_engine as _create_sync_engine
from api.settings import settings


def create_async_engine() -> AsyncEngine:
  return _create_async_engine(dsn=settings.get_sqlite_dsn("aiosqlite"), debug=False)


def create_sync_engine() -> Engine:
  return _create_sync_engine(dsn=settings.get_sqlite_dsn("pysqlite"), debug=False)


class AsyncSessionMiddleware:
  def __init__(self, app: ASGIApp) -> None:
    self.app = app

  async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] not in ("http", "websocket"):
      return await self.app(scope, receive, send)

    sessionmaker: AsyncSessionMaker = scope["state"]["async_sessionmaker"]
    async with sessionmaker() as session:
      scope["state"]["async_session"] = session
      await self.app(scope, receive, send)


async def get_db_sessionmaker(request: Request) -> AsyncSessionMaker:
  return request.state.async_sessionmaker


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession]:
  try:
    session = request.state.async_session
  except AttributeError as e:
    raise RuntimeError("Session is not present in the request state. Did you forget to add AsyncSessionMiddleware?") from e

  try:
    yield session
  except Exception:
    await session.rollback()
    raise
  else:
    await session.commit()


__all__ = [
  "AsyncEngine",
  "AsyncSession",
  "create_async_engine",
  "create_sync_engine",
  "get_db_session",
  "get_db_sessionmaker",
]
