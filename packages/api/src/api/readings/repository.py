from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Integer, cast, func, select

from api.common.repository.base import RepositoryBase, RepositoryIDMixin
from api.models.reading import Reading


class ReadingRepository(RepositoryBase[Reading], RepositoryIDMixin[Reading, UUID]):
  model = Reading

  async def get_latest(self) -> Reading | None:
    statement = self.get_base_statement().order_by(Reading.created_at.desc()).limit(1)
    return await self.get_one_or_none(statement)

  async def get_soc_buckets(self, bucket_seconds: int, window_start: datetime) -> Sequence[tuple[int, float]]:
    """Average soc_percent per bucket_seconds-wide time bucket, for readings at
    or after window_start. Buckets with no readings are simply absent."""
    epoch = cast(func.strftime("%s", Reading.created_at), Integer)
    bucket_epoch = (epoch - (epoch % bucket_seconds)).label("bucket_epoch")
    statement = select(bucket_epoch, func.avg(Reading.soc_percent)).where(Reading.created_at >= window_start).group_by(bucket_epoch).order_by(bucket_epoch)
    result = await self.session.execute(statement)
    return [(row[0], row[1]) for row in result.all()]

  async def get_soc_before(self, before: datetime) -> float | None:
    """The most recent soc_percent strictly before `before`, used to seed
    carry-forward for a history window that starts mid-gap."""
    statement = select(Reading.soc_percent).where(Reading.created_at < before).order_by(Reading.created_at.desc()).limit(1)
    result = await self.session.execute(statement)
    return result.scalar_one_or_none()
