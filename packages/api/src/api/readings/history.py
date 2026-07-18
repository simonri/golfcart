"""Buckets SOC readings into fixed-width time windows for the dashboard history
chart. A bucket with no reading in it carries forward the last known value
(has_data=False) instead of leaving a hole - the frontend renders those bars
gray.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from api.common.schemas import Schema

BUCKET_COUNT = 30


class HistoryPeriod(StrEnum):
  five_min = "5m"
  one_hour = "1h"

  @property
  def bucket_seconds(self) -> int:
    return 300 if self is HistoryPeriod.five_min else 3600


class SocHistoryBucketSchema(Schema):
  bucket_start: datetime = Field(description="Start of this bucket, UTC.")
  soc_percent: float | None = Field(
    description="Average state of charge in this bucket, or the last known value carried forward when the bucket has no readings."
  )
  has_data: bool = Field(description="Whether a reading actually fell in this bucket.")


class SocHistoryResponse(Schema):
  buckets: list[SocHistoryBucketSchema] = Field(description=f"The most recent {BUCKET_COUNT} buckets, oldest first.")


def build_soc_history(
  raw_buckets: Sequence[tuple[int, float]],
  seed_soc: float | None,
  period: HistoryPeriod,
  now: datetime,
) -> list[SocHistoryBucketSchema]:
  bucket_seconds = period.bucket_seconds
  raw_by_epoch = dict(raw_buckets)

  now_epoch = int(now.timestamp())
  latest_epoch = now_epoch - (now_epoch % bucket_seconds)
  start_epoch = latest_epoch - bucket_seconds * (BUCKET_COUNT - 1)

  buckets: list[SocHistoryBucketSchema] = []
  carry = seed_soc
  for i in range(BUCKET_COUNT):
    epoch = start_epoch + i * bucket_seconds
    raw_value = raw_by_epoch.get(epoch)
    has_data = raw_value is not None
    if has_data:
      carry = raw_value
    buckets.append(
      SocHistoryBucketSchema(
        bucket_start=datetime.fromtimestamp(epoch, tz=UTC),
        soc_percent=raw_value if has_data else carry,
        has_data=has_data,
      )
    )
  return buckets
