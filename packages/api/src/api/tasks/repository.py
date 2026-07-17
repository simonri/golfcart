from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from api.common.repository.base import RepositoryBase, RepositoryIDMixin
from api.models.task import Task


class TaskRepository(RepositoryBase[Task], RepositoryIDMixin[Task, UUID]):
  model = Task

  async def get_max_position(self) -> float | None:
    result = await self.session.execute(select(func.max(Task.position)))
    return result.scalar()

  async def list_by_ids(self, task_ids: Sequence[UUID]) -> Sequence[Task]:
    return await self.get_all(self.get_base_statement().where(Task.id.in_(task_ids)))

  async def list_areas_by_usage(self) -> list[str]:
    result = await self.session.execute(select(Task.area).where(Task.area.is_not(None)).group_by(Task.area).order_by(func.count().desc()))
    return [row[0] for row in result.all()]
