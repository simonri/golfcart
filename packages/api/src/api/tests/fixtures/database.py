import tempfile
from collections.abc import AsyncIterator, Callable, Coroutine
from pathlib import Path

import pytest
import pytest_asyncio
from api.common.db.engine import create_async_engine
from api.models.base import Model
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession


def get_database_url(worker_id: str) -> str:
  db_path = Path(tempfile.gettempdir()) / f"golfcart_test_{worker_id}.db"
  return f"sqlite+aiosqlite:///{db_path}"


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def initialize_test_database(worker_id: str) -> AsyncIterator[None]:
  db_path = Path(tempfile.gettempdir()) / f"golfcart_test_{worker_id}.db"
  db_path.unlink(missing_ok=True)

  engine = create_async_engine(dsn=get_database_url(worker_id))
  async with engine.begin() as conn:
    await conn.run_sync(Model.metadata.create_all)
  await engine.dispose()

  yield

  db_path.unlink(missing_ok=True)


@pytest_asyncio.fixture
async def session(worker_id: str, mocker: MockerFixture) -> AsyncIterator[AsyncSession]:
  engine = create_async_engine(dsn=get_database_url(worker_id))
  connection = await engine.connect()
  transaction = await connection.begin()

  session = AsyncSession(bind=connection, expire_on_commit=False)

  yield session

  await transaction.rollback()
  await connection.close()
  await engine.dispose()


SaveFixture = Callable[[Model], Coroutine[None, None, None]]


def save_fixture_factory(session: AsyncSession) -> SaveFixture:
  async def _save_fixture(model: Model) -> None:
    session.add(model)
    await session.flush()

  return _save_fixture


@pytest.fixture
def save_fixture(session: AsyncSession) -> SaveFixture:
  return save_fixture_factory(session)
