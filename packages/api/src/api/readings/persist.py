from dataclasses import asdict

from api.database import AsyncSession
from api.models.reading import Reading
from api.readings.bms import PROTOCOL, CaptureResult
from api.readings.repository import ReadingRepository


def build_reading(result: CaptureResult) -> Reading:
  decoded = result.decoded
  return Reading(
    device_name=result.device_name,
    device_address=result.device_address,
    device_model=decoded.device_model,
    protocol=PROTOCOL,
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
      "protocol": PROTOCOL,
      "raw_blocks": result.blocks,
      "decoded": asdict(decoded),
    },
  )


async def persist_reading(session: AsyncSession, result: CaptureResult) -> Reading:
  reading = build_reading(result)
  await ReadingRepository.from_session(session).create(reading, flush=True)
  return reading
