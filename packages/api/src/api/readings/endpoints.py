from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from api.common.pagination import PaginationParamsQuery
from api.common.sorting import Sorting, SortingGetter
from api.database import AsyncSession, get_db_session
from api.exceptions import ResourceNotFound, ServiceUnavailableError
from api.models.reading import Reading
from api.readings.bms import BmsUnreachableError
from api.readings.connection import connection
from api.readings.persist import persist_reading
from api.readings.repository import ReadingRepository
from api.readings.schemas import ReadingListResponse, ReadingSchema

router = APIRouter(prefix="/readings", tags=["readings"])


class ReadingSortProperty(StrEnum):
  created_at = "created_at"
  voltage_v = "voltage_v"
  soc_percent = "soc_percent"


sorting_getter = SortingGetter(ReadingSortProperty, default_sorting=["-created_at"])


@router.post(
  "",
  summary="Capture Reading",
  response_model=ReadingSchema,
  status_code=201,
)
async def create_reading(
  session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReadingSchema:
  try:
    result = await connection.read_now()
  except BmsUnreachableError as e:
    raise ServiceUnavailableError(f"BMS unreachable: {e}") from e

  reading = await persist_reading(session, result)
  return ReadingSchema.model_validate(reading)


@router.get(
  "",
  summary="List Readings",
  response_model=ReadingListResponse,
)
async def list_readings(
  session: Annotated[AsyncSession, Depends(get_db_session)],
  pagination: PaginationParamsQuery,
  sorting: Annotated[list[Sorting[ReadingSortProperty]], Depends(sorting_getter)],
  created_after: int | None = Query(default=None, description="Filter readings created after this Unix timestamp (inclusive)."),
  created_before: int | None = Query(default=None, description="Filter readings created before this Unix timestamp (exclusive)."),
  has_alarms: bool | None = Query(default=None, description="Filter by alarm presence."),
) -> ReadingListResponse:
  repo = ReadingRepository.from_session(session)
  statement = repo.get_base_statement()

  if created_after is not None:
    statement = statement.where(Reading.created_at >= datetime.fromtimestamp(created_after, tz=UTC))
  if created_before is not None:
    statement = statement.where(Reading.created_at < datetime.fromtimestamp(created_before, tz=UTC))
  if has_alarms is not None:
    statement = statement.where(Reading.has_alarms == has_alarms)

  for prop, desc in sorting:
    column = getattr(Reading, prop.value)
    statement = statement.order_by(column.desc() if desc else column.asc())

  items, total_count = await repo.paginate(statement, limit=pagination.limit, page=pagination.page)
  return ReadingListResponse.from_paginated_results(
    [ReadingSchema.model_validate(item) for item in items],
    total_count,
    pagination,
  )


# Registered before /{reading_id} — FastAPI matches routes in definition order,
# and "/latest" would otherwise be captured (and 422) as a reading_id.
@router.get(
  "/latest",
  summary="Get Latest Reading",
  response_model=ReadingSchema,
)
async def get_latest_reading(
  session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReadingSchema:
  reading = await ReadingRepository.from_session(session).get_latest()
  if reading is None:
    raise ResourceNotFound("No readings yet")
  return ReadingSchema.model_validate(reading)


@router.get(
  "/{reading_id}",
  summary="Get Reading",
  response_model=ReadingSchema,
)
async def get_reading(
  reading_id: UUID,
  session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReadingSchema:
  reading = await ReadingRepository.from_session(session).get_by_id(reading_id)
  if reading is None:
    raise ResourceNotFound("Reading not found")
  return ReadingSchema.model_validate(reading)
