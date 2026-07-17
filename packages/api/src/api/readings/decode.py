"""Pure decoding of Daly Modbus-BLE register blocks into structured readings.

Register layout (main block 0x0000): cells at 0-31 (mV), temperature sensors at
32-39 (offset -40 °C), pack metrics at 40-57, alarm registers at 58-61, and an
extended balancing section at 62+. Currents are encoded with a 30000 offset in
units of 0.1 A.
"""

import struct
from dataclasses import dataclass
from typing import Any

MODE_NAMES = {0: "idle", 1: "charging", 2: "discharging"}
UNUSED = 0xFFFF

MAIN_BLOCK = "main_0x0000"
INFO_BLOCK = "info_0x0050"
SETTINGS_BLOCK = "settings_0x0080"

# Alarm registers 58-61 (Alarm1-4) form one 64-bit bitmask, MSB-first
# (Alarm1 << 48 | Alarm2 << 32 | Alarm3 << 16 | Alarm4). Bit-to-message mapping
# reverse-engineered by https://github.com/syssi/esphome-daly-bms (not officially
# documented by Daly); "" marks unused bits, "Reserved" marks bits Daly reserved
# but hasn't assigned a meaning to.
ALARM_MESSAGES: tuple[str, ...] = (
  *([""] * 16),  # Alarm4 (register 61): unused
  "Charging MOS over-temperature warning",
  "Discharging MOS over-temperature warning",
  "Charging MOS temperature sensor failure",
  "Discharging MOS temperature sensor failure",
  "Charging MOS adhesion failure",
  "Discharging MOS adhesion failure",
  "Charging MOS circuit fault",
  "Discharging MOS circuit fault",
  "AFE acquisition chip failure",
  "Single unit collection is offline",
  "Single temperature sensor failure",
  "EEPROM storage failure",
  "RTC clock failure",
  "Precharge failed",
  "Vehicle communication failed",
  "Internal network communication module failure",
  "Warning: Charging current too high",
  "Critical: Charging current too high",
  "Warning: Discharging current too low",
  "Critical: Discharging current too low",
  "Warning: SOC too high",
  "Critical: SOC too high",
  "Warning: SOC too low",
  "Critical: SOC too low",
  "Warning: Voltage difference too high",
  "Critical: Voltage difference too high",
  "Warning: Temperature difference too high",
  "Critical: Temperature difference too high",
  "Reserved",
  "Reserved",
  "Reserved",
  "Reserved",
  "Warning: Cell voltage too high",
  "Critical: Cell voltage too high",
  "Warning: Cell voltage too low",
  "Critical: Cell voltage too low",
  "Warning: Total voltage too high",
  "Critical: Total voltage too high",
  "Warning: Total voltage too low",
  "Critical: Total voltage too low",
  "Warning: Charging temperature too high",
  "Critical: Charging temperature too high",
  "Warning: Charging temperature too low",
  "Critical: Charging temperature too low",
  "Warning: Discharging temperature too high",
  "Critical: Discharging temperature too high",
  "Warning: Discharging temperature too low",
  "Critical: Discharging temperature too low",
)


def decode_alarm_messages(alarm1: int, alarm2: int, alarm3: int, alarm4: int) -> list[str] | None:
  mask = (alarm1 << 48) | (alarm2 << 32) | (alarm3 << 16) | alarm4
  if not mask:
    return None
  return [message for i, message in enumerate(ALARM_MESSAGES) if mask & (1 << i) and message]


def bitmask_to_cells(mask: int) -> list[int]:
  return [i + 1 for i in range(16) if mask & (1 << i)]


@dataclass
class DecodedBalancing:
  balance_current_a: float
  balancing_cells: list[int]
  mosfet_temperature_c: float | None = None
  board_temperature_c: float | None = None


@dataclass
class DecodedReading:
  voltage_v: float
  current_a: float
  power_w: float
  soc_percent: float
  remaining_capacity_ah: float
  rated_capacity_ah: float | None
  mode: str
  cycles: int
  cell_count: int
  cell_voltages: list[float]
  cell_voltage_max_v: float
  cell_voltage_min_v: float
  cell_voltage_avg_v: float
  cell_voltage_delta_v: float
  temperature_sensor_count: int
  temperatures: list[float]
  temperature_max_c: float
  temperature_min_c: float
  balancer_active: bool
  charging_mosfet: bool
  discharging_mosfet: bool
  alarms: dict[str, str] | None
  alarm_messages: list[str] | None
  balancing: DecodedBalancing | None
  device_model: str | None


def decode_blocks(blocks: dict[str, Any]) -> DecodedReading:
  regs = blocks[MAIN_BLOCK]["registers"]
  cell_count = regs[49]
  sensor_count = regs[50]
  voltage = regs[40] / 10
  current = (regs[41] - 30000) / 10

  alarms = {f"alarm_register_{i}": f"0x{regs[58 + i]:04x}" for i in range(4)} if any(regs[58:62]) else None
  alarm_messages = decode_alarm_messages(regs[58], regs[59], regs[60], regs[61])

  balancing = None
  if len(regs) > 66:  # extended part of the main block
    balancing = DecodedBalancing(
      balance_current_a=(regs[64] - 30000) / 10,
      balancing_cells=bitmask_to_cells(regs[65]),
    )
    if regs[66] != UNUSED:
      balancing.mosfet_temperature_c = regs[66] - 40
    if len(regs) > 67 and regs[67] != UNUSED:
      balancing.board_temperature_c = regs[67] - 40

  device_model = None
  if info := blocks.get(INFO_BLOCK):
    raw = struct.pack(f">{len(info['registers'])}H", *info["registers"])
    device_model = raw.strip(b"\x00\xff").decode("ascii", errors="replace")

  rated_capacity_ah = None
  if settings_block := blocks.get(SETTINGS_BLOCK):
    rated_capacity_ah = settings_block["registers"][0] / 10

  return DecodedReading(
    voltage_v=voltage,
    current_a=current,
    power_w=round(voltage * current, 1),
    soc_percent=regs[42] / 10,
    remaining_capacity_ah=regs[48] / 10,
    rated_capacity_ah=rated_capacity_ah,
    mode=MODE_NAMES.get(regs[47], str(regs[47])),
    cycles=regs[51],
    cell_count=cell_count,
    cell_voltages=[regs[i] / 1000 for i in range(cell_count)],
    cell_voltage_max_v=regs[43] / 1000,
    cell_voltage_min_v=regs[44] / 1000,
    cell_voltage_avg_v=regs[55] / 1000,
    cell_voltage_delta_v=regs[56] / 1000,
    temperature_sensor_count=sensor_count,
    temperatures=[regs[32 + i] - 40 for i in range(sensor_count)],
    temperature_max_c=regs[45] - 40,
    temperature_min_c=regs[46] - 40,
    balancer_active=bool(regs[52]),
    charging_mosfet=bool(regs[53]),
    discharging_mosfet=bool(regs[54]),
    alarms=alarms,
    alarm_messages=alarm_messages,
    balancing=balancing,
    device_model=device_model,
  )
