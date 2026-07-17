from uuid import UUID

from api.common.repository.base import RepositoryBase, RepositoryIDMixin
from api.models.reading import Reading


class ReadingRepository(RepositoryBase[Reading], RepositoryIDMixin[Reading, UUID]):
  model = Reading

  async def get_latest(self) -> Reading | None:
    statement = self.get_base_statement().order_by(Reading.created_at.desc()).limit(1)
    return await self.get_one_or_none(statement)
