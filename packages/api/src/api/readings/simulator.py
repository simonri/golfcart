"""Simulated Daly BMS for local development where no Bluetooth hardware is
available. Enabled via BMS_SIMULATOR; BmsConnection then swaps the BLE client
for these stand-ins and everything downstream runs unchanged.

Duck-types DalyModbusBLE's read interface but synthesizes register blocks from
a time-driven battery model: the pack discharges from full down to SOC_MIN,
then charges back up, repeating every BMS_SIMULATOR_CYCLE_S seconds. The phase
derives from wall-clock time, so an API restart resumes mid-cycle instead of
snapping back to full. Near the bottom of the cycle the "SOC too low" alarm
bit is raised, and near the top the balancer kicks in, so those UI states get
exercised too.

Blocks are encoded exactly as the real BMS sends them (CRC-valid frames, the
30000-offset current encoding, -40 temperature offsets), so decoding and raw
persistence behave as in production.
"""

import math
import struct
import time
from typing import Any

from api.readings.bms import crc16_modbus
from api.readings.decode import INFO_BLOCK, MAIN_BLOCK, SETTINGS_BLOCK, UNUSED
from api.settings import settings

SIMULATOR_ADDRESS = "SIM:00:00:00:00:00"

CELL_COUNT = 14
RATED_CAPACITY_AH = 50.0
SOC_MIN = 20.0
DISCHARGE_FRACTION = 0.6  # of the cycle; the rest charges back up
LOW_SOC_WARNING_THRESHOLD = 25.0
BALANCING_SOC_THRESHOLD = 95.0
CELL_RESISTANCE_OHM = 0.0015

# NMC open-circuit voltage per cell, piecewise-linear over SOC.
_OCV_POINTS = (
  (0.0, 3.20),
  (10.0, 3.48),
  (20.0, 3.60),
  (30.0, 3.67),
  (40.0, 3.72),
  (50.0, 3.77),
  (60.0, 3.83),
  (70.0, 3.90),
  (80.0, 3.97),
  (90.0, 4.05),
  (100.0, 4.15),
)

# Bit 38 of the combined 64-bit alarm mask ("Warning: SOC too low") lives in
# Alarm2 (register 59), which covers bits 32-47.
_ALARM2_SOC_TOO_LOW = 1 << (38 - 32)


def _cell_ocv(soc: float) -> float:
  for (soc_lo, v_lo), (soc_hi, v_hi) in zip(_OCV_POINTS, _OCV_POINTS[1:], strict=False):
    if soc <= soc_hi:
      return v_lo + (v_hi - v_lo) * (soc - soc_lo) / (soc_hi - soc_lo)
  return _OCV_POINTS[-1][1]


def _battery_state(now: float) -> tuple[float, float]:
  """Returns (soc_percent, current_a) for a wall-clock instant; current is
  negative while discharging."""
  cycle = settings.BMS_SIMULATOR_CYCLE_S
  phase = (now % cycle) / cycle
  if phase < DISCHARGE_FRACTION:
    soc = 100.0 - (100.0 - SOC_MIN) * (phase / DISCHARGE_FRACTION)
    # Driving load: a base draw with slow ripple, as if terrain varies.
    current = -(35.0 + 8.0 * math.sin(now / 9.0) + 4.0 * math.sin(now / 23.0))
  else:
    charge_progress = (phase - DISCHARGE_FRACTION) / (1.0 - DISCHARGE_FRACTION)
    soc = SOC_MIN + (100.0 - SOC_MIN) * charge_progress
    # Constant-current charge, tapering off above 90% as a CV stage would.
    current = 25.0 if soc <= 90.0 else max(2.0, 25.0 * (100.0 - soc) / 10.0)
  return soc, current


def _encode_block(start: int, registers: list[int]) -> dict[str, Any]:
  payload = struct.pack(f">{len(registers)}H", *registers)
  frame = struct.pack(">BBB", 0xD2, 0x03, len(payload)) + payload
  frame += struct.pack("<H", crc16_modbus(frame))
  return {"request": {"start": start, "count": len(registers)}, "frame_hex": frame.hex(), "registers": registers}


def build_blocks(now: float) -> dict[str, Any]:
  soc, current = _battery_state(now)

  ocv = _cell_ocv(soc)
  loaded = ocv + current * CELL_RESISTANCE_OHM
  cell_mv = [round(loaded * 1000) + (i * 37) % 15 - 7 + round(3 * math.sin(now / 60.0 + i)) for i in range(CELL_COUNT)]
  pack_v = sum(cell_mv) / 1000

  temperature_c = round(21 + abs(current) * 0.15)
  temperatures = [temperature_c, temperature_c + 1]

  balancer_active = current > 0 and soc >= BALANCING_SOC_THRESHOLD
  max_mv = max(cell_mv)
  balancing_mask = sum(1 << i for i, mv in enumerate(cell_mv) if mv >= max_mv - 3) if balancer_active else 0

  if current > 0.5:
    mode = 1
  elif current < -0.5:
    mode = 2
  else:
    mode = 0

  regs = [0] * 68
  regs[:CELL_COUNT] = cell_mv
  regs[32 : 32 + len(temperatures)] = [t + 40 for t in temperatures]
  regs[40] = round(pack_v * 10)
  regs[41] = round(current * 10) + 30000
  regs[42] = round(soc * 10)
  regs[43] = max_mv
  regs[44] = min(cell_mv)
  regs[45] = max(temperatures) + 40
  regs[46] = min(temperatures) + 40
  regs[47] = mode
  regs[48] = round(soc / 100 * RATED_CAPACITY_AH * 10)
  regs[49] = CELL_COUNT
  regs[50] = len(temperatures)
  regs[51] = 12
  regs[52] = int(balancer_active)
  regs[53] = 1
  regs[54] = 1
  regs[55] = round(sum(cell_mv) / len(cell_mv))
  regs[56] = max_mv - min(cell_mv)
  regs[59] = _ALARM2_SOC_TOO_LOW if soc < LOW_SOC_WARNING_THRESHOLD else 0
  regs[64] = 30000 + (3 if balancer_active else 0)
  regs[65] = balancing_mask
  regs[66] = max(temperatures) + 1 + 40
  regs[67] = UNUSED

  model = b"DL-SIMULATOR".ljust(0x20 * 2, b"\x00")
  info_regs = list(struct.unpack(f">{0x20}H", model))

  settings_regs = [0] * 0x10
  settings_regs[0] = round(RATED_CAPACITY_AH * 10)

  return {
    MAIN_BLOCK: _encode_block(0x0000, regs),
    INFO_BLOCK: _encode_block(0x0050, info_regs),
    SETTINGS_BLOCK: _encode_block(0x0080, settings_regs),
  }


class SimulatedClient:
  """Stands in for BleakClient so BmsConnection's is_connected checks and
  disconnect paths work unchanged."""

  def __init__(self) -> None:
    self.is_connected = True

  async def disconnect(self) -> None:
    self.is_connected = False


class SimulatedDalyBms:
  """Drop-in for DalyModbusBLE (the surface BmsConnection uses)."""

  async def start(self) -> None:
    pass

  async def read_all(self) -> dict[str, Any]:
    return build_blocks(time.time())
