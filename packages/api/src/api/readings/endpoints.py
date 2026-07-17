from dataclasses import asdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from api.common.pagination import PaginationParamsQuery
from api.common.sorting import Sorting, SortingGetter
from api.database import AsyncSession, get_db_session
from api.exceptions import ConflictError, ResourceNotFound, ServiceUnavailableError
from api.models.reading import Reading
from api.readings import bms
from api.readings.bms import BmsUnreachableError, CaptureResult
from api.readings.repository import ReadingRepository
from api.readings.schemas import ReadingListResponse, ReadingSchema

router = APIRouter(prefix="/readings", tags=["readings"])


class ReadingSortProperty(StrEnum):
  created_at = "created_at"
  voltage_v = "voltage_v"
  soc_percent = "soc_percent"


sorting_getter = SortingGetter(ReadingSortProperty, default_sorting=["-created_at"])


def _build_reading(result: CaptureResult) -> Reading:
  decoded = result.decoded
  return Reading(
    device_name=result.device_name,
    device_address=result.device_address,
    device_model=decoded.device_model,
    protocol=bms.PROTOCOL,
    voltage_v=decoded.voltage_v,
    current_a=decoded.current_a,
    power_w=decoded.power_w,
    soc_percent=decoded.soc_percent,
    remaining_capacity_ah=decoded.remaining_capacity_ah,
    rated_capacity_ah=decoded.rated_capacity_ah,
    mode=decoded.mode,
    cycles=decoded.cycles,
    cell_count=decoded.cell_count,
    cell_voltage_max_v=decoded.cell_voltage_max_v,
    cell_voltage_min_v=decoded.cell_voltage_min_v,
    cell_voltage_avg_v=decoded.cell_voltage_avg_v,
    cell_voltage_delta_v=decoded.cell_voltage_delta_v,
    temperature_sensor_count=decoded.temperature_sensor_count,
    temperature_max_c=decoded.temperature_max_c,
    temperature_min_c=decoded.temperature_min_c,
    balancer_active=decoded.balancer_active,
    charging_mosfet=decoded.charging_mosfet,
    discharging_mosfet=decoded.discharging_mosfet,
    has_alarms=decoded.alarms is not None,
    cell_voltages=decoded.cell_voltages,
    temperatures=decoded.temperatures,
    balancing=asdict(decoded.balancing) if decoded.balancing else None,
    alarms=decoded.alarms,
    alarm_messages=decoded.alarm_messages,
    raw={
      "device": {"name": result.device_name, "address": result.device_address},
      "protocol": bms.PROTOCOL,
      "raw_blocks": result.blocks,
      "decoded": asdict(decoded),
    },
  )


@router.post(
  "",
  summary="Capture Reading",
  response_model=ReadingSchema,
  status_code=201,
)
async def create_reading(
  session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReadingSchema:
  if bms.capture_lock.locked():
    raise ConflictError("A BMS capture is already in progress")

  async with bms.capture_lock:
    try:
      result = await bms.capture_reading()
    except BmsUnreachableError as e:
      raise ServiceUnavailableError(f"BMS unreachable: {e}") from e

  reading = _build_reading(result)
  await ReadingRepository.from_session(session).create(reading, flush=True)
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
