from pydantic import Field

from api.common.pagination import ListResource
from api.common.schemas import IDSchema, Schema, TimestampedSchema


class BalancingSchema(Schema):
  balance_current_a: float = Field(description="Balancer current in amperes.")
  balancing_cells: list[int] = Field(description="1-based numbers of the cells currently being balanced.")
  mosfet_temperature_c: float | None = Field(default=None, description="Balancer MOSFET temperature in °C.")
  board_temperature_c: float | None = Field(default=None, description="Balancer board temperature in °C.")


class ReadingSchema(IDSchema, TimestampedSchema):
  device_name: str | None = Field(description="Bluetooth name of the BMS device.")
  device_address: str = Field(description="Bluetooth address of the BMS device.")
  device_model: str | None = Field(description="BMS model string reported by the device.")
  protocol: str = Field(description="Protocol used to read the BMS.")

  voltage_v: float = Field(description="Total pack voltage in volts.")
  current_a: float = Field(description="Pack current in amperes; positive when charging, negative when discharging.")
  power_w: float = Field(description="Pack power in watts.")
  soc_percent: float = Field(description="State of charge in percent.")
  remaining_capacity_ah: float = Field(description="Remaining capacity in ampere-hours.")
  rated_capacity_ah: float | None = Field(description="Rated capacity in ampere-hours, from the BMS settings.")
  mode: str = Field(description="Pack mode: idle, charging or discharging.")
  cycles: int = Field(description="Charge cycle count.")

  cell_count: int = Field(description="Number of cells in the pack.")
  cell_voltage_max_v: float = Field(description="Highest cell voltage in volts.")
  cell_voltage_min_v: float = Field(description="Lowest cell voltage in volts.")
  cell_voltage_avg_v: float = Field(description="Average cell voltage in volts.")
  cell_voltage_delta_v: float = Field(description="Difference between highest and lowest cell voltage in volts.")

  temperature_sensor_count: int = Field(description="Number of temperature sensors.")
  temperature_max_c: float = Field(description="Highest sensor temperature in °C.")
  temperature_min_c: float = Field(description="Lowest sensor temperature in °C.")

  balancer_active: bool = Field(description="Whether the balancer is active.")
  charging_mosfet: bool = Field(description="Whether the charging MOSFET is enabled.")
  discharging_mosfet: bool = Field(description="Whether the discharging MOSFET is enabled.")
  has_alarms: bool = Field(description="Whether any alarm register is set.")

  cell_voltages: list[float] = Field(description="Per-cell voltages in volts, ordered by cell number.")
  temperatures: list[float] = Field(description="Per-sensor temperatures in °C, ordered by sensor number.")
  balancing: BalancingSchema | None = Field(description="Balancing details, if reported by the BMS.")
  alarms: dict[str, str] | None = Field(description="Raw alarm registers as hex strings, or null when no alarms are set.")
  alarm_messages: list[str] | None = Field(description="Human-readable alarm/warning messages decoded from the alarm registers.")


class ReadingListResponse(ListResource[ReadingSchema]):
  pass
