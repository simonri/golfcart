from typing import Any

from api.models.reading import Reading

__all__ = ["create_reading"]


def create_reading(**overrides: Any) -> Reading:
  defaults: dict[str, Any] = {
    "device_name": "DL-411905019B59",
    "device_address": "AA:BB:CC:DD:EE:FF",
    "device_model": "226KF270201240",
    "protocol": "daly-modbus-ble",
    "voltage_v": 56.6,
    "current_a": 17.6,
    "power_w": 996.2,
    "soc_percent": 42.6,
    "remaining_capacity_ah": 21.3,
    "rated_capacity_ah": 50.0,
    "mode": "charging",
    "cycles": 2,
    "cell_count": 14,
    "cell_voltage_max_v": 4.073,
    "cell_voltage_min_v": 3.981,
    "cell_voltage_avg_v": 4.051,
    "cell_voltage_delta_v": 0.092,
    "temperature_sensor_count": 2,
    "temperature_max_c": 33,
    "temperature_min_c": 33,
    "balancer_active": True,
    "charging_mosfet": True,
    "discharging_mosfet": True,
    "has_alarms": False,
    "cell_voltages": [4.0] * 14,
    "temperatures": [33, 33],
    "balancing": None,
    "alarms": None,
    "raw": {},
  }
  return Reading(**{**defaults, **overrides})
