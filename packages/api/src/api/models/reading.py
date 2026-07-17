from typing import Any

from sqlalchemy import JSON, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import RecordModel


class Reading(RecordModel):
  __tablename__ = "readings"

  # Device
  device_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
  device_address: Mapped[str] = mapped_column(String(100), nullable=False)
  device_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
  protocol: Mapped[str] = mapped_column(String(30), nullable=False)

  # Pack
  voltage_v: Mapped[float] = mapped_column(Float, nullable=False)
  current_a: Mapped[float] = mapped_column(Float, nullable=False)
  power_w: Mapped[float] = mapped_column(Float, nullable=False)
  soc_percent: Mapped[float] = mapped_column(Float, nullable=False)
  remaining_capacity_ah: Mapped[float] = mapped_column(Float, nullable=False)
  rated_capacity_ah: Mapped[float | None] = mapped_column(Float, nullable=True)
  mode: Mapped[str] = mapped_column(String(20), nullable=False)
  cycles: Mapped[int] = mapped_column(Integer, nullable=False)

  # Cell voltages
  cell_count: Mapped[int] = mapped_column(Integer, nullable=False)
  cell_voltage_max_v: Mapped[float] = mapped_column(Float, nullable=False)
  cell_voltage_min_v: Mapped[float] = mapped_column(Float, nullable=False)
  cell_voltage_avg_v: Mapped[float] = mapped_column(Float, nullable=False)
  cell_voltage_delta_v: Mapped[float] = mapped_column(Float, nullable=False)

  # Temperatures
  temperature_sensor_count: Mapped[int] = mapped_column(Integer, nullable=False)
  temperature_max_c: Mapped[float] = mapped_column(Float, nullable=False)
  temperature_min_c: Mapped[float] = mapped_column(Float, nullable=False)

  # Status
  balancer_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
  charging_mosfet: Mapped[bool] = mapped_column(Boolean, nullable=False)
  discharging_mosfet: Mapped[bool] = mapped_column(Boolean, nullable=False)
  has_alarms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

  # Detail; cell_voltages and temperatures are ordered lists (index = cell/sensor number - 1)
  cell_voltages: Mapped[list[float]] = mapped_column(JSON, nullable=False)
  temperatures: Mapped[list[float]] = mapped_column(JSON, nullable=False)
  balancing: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
  alarms: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
  alarm_messages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
  raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
