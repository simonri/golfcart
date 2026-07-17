"""Bluetooth LE protocol/transport for Daly BMS boards speaking the Modbus-style
protocol on the fff0 UART service.

All bleak I/O is confined to this module. Connection lifecycle (persistent
connect, reconnect, polling) lives in `api.readings.connection` — this module
only knows how to scan, frame requests, and parse responses.
"""

import asyncio
import struct
import time
from dataclasses import dataclass
from typing import Any

import structlog
from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from api.readings.decode import MAIN_BLOCK, DecodedReading
from api.settings import settings

# NOTE: plain `logging.getLogger(__name__)` is silently dropped in production —
# api.logging's dictConfig runs with disable_existing_loggers=True *after* this
# module is imported, which disables any stdlib logger created before it.
# structlog.get_logger() defers real logger creation until first use, avoiding it.
log = structlog.get_logger()

SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"

PROTOCOL = "daly-modbus-ble"

# register blocks the BMS answers (name, start, count, fallback count)
BLOCK_MAIN = (MAIN_BLOCK, 0x0000, 0x50, 0x3E)
BLOCK_INFO = ("info_0x0050", 0x0050, 0x20, None)
BLOCK_SETTINGS = ("settings_0x0080", 0x0080, 0x10, None)


class BmsUnreachableError(Exception):
  """The BMS could not be found, connected to, or read."""


@dataclass
class CaptureResult:
  device_name: str | None
  device_address: str
  blocks: dict[str, Any]
  decoded: DecodedReading


def crc16_modbus(data: bytes) -> int:
  crc = 0xFFFF
  for byte in data:
    crc ^= byte
    for _ in range(8):
      crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
  return crc


def modbus_request(start: int, count: int) -> bytes:
  frame = struct.pack(">BBHH", 0xD2, 0x03, start, count)
  return frame + struct.pack("<H", crc16_modbus(frame))


def looks_like_daly(name: str | None) -> bool:
  if not name:
    return False
  upper = name.upper()
  return upper.startswith("DL-") or "DALY" in upper


class DalyModbusBLE:
  """Wraps a connected BleakClient to speak the modbus-over-notify protocol.
  Does not own the connection's lifecycle — caller connects/disconnects."""

  def __init__(self, client: Any):
    self.client = client
    self._buffer = bytearray()
    self._future: asyncio.Future[bytes] | None = None

  async def start(self) -> None:
    await self.client.start_notify(NOTIFY_UUID, self._on_notify)

  def _on_notify(self, sender: Any, data: bytearray) -> None:
    self._buffer.extend(data)
    if len(self._buffer) < 3:
      return
    expected = 3 + self._buffer[2] + 2  # header + payload + crc
    if len(self._buffer) >= expected and self._future and not self._future.done():
      self._future.set_result(bytes(self._buffer[:expected]))

  async def read_registers(self, start: int, count: int) -> tuple[str, list[int]]:
    """Read `count` 16-bit registers from `start`; returns (frame_hex, registers)."""
    self._buffer.clear()
    self._future = asyncio.get_running_loop().create_future()
    await self.client.write_gatt_char(WRITE_UUID, modbus_request(start, count), response=True)
    frame = await asyncio.wait_for(self._future, settings.BMS_RESPONSE_TIMEOUT)

    if frame[0] != 0xD2 or frame[1] != 0x03:
      raise ValueError(f"unexpected frame header: {frame[:3].hex()}")
    crc = struct.unpack("<H", frame[-2:])[0]
    if crc != crc16_modbus(frame[:-2]):
      raise ValueError("CRC mismatch in BMS response")
    payload = frame[3:-2]
    return frame.hex(), list(struct.unpack(f">{len(payload) // 2}H", payload))

  async def read_block(self, name: str, start: int, count: int, fallback_count: int | None = None) -> dict[str, Any] | None:
    started = time.monotonic()
    try:
      frame_hex, regs = await self.read_registers(start, count)
    except (TimeoutError, ValueError) as e:
      if fallback_count is None:
        log.warning("bms.block.unavailable", block=name, error=str(e) or "timeout", duration_s=round(time.monotonic() - started, 2))
        return None
      log.info("bms.block.retry_with_fallback", block=name, count=count, fallback_count=fallback_count)
      count = fallback_count
      frame_hex, regs = await self.read_registers(start, count)
    log.info("bms.block.read", block=name, count=count, duration_s=round(time.monotonic() - started, 2))
    return {
      "request": {"start": start, "count": count},
      "frame_hex": frame_hex,
      "registers": regs,
    }

  async def read_all(self) -> dict[str, Any]:
    started = time.monotonic()
    blocks = {}
    for name, start, count, fallback in (BLOCK_MAIN, BLOCK_INFO, BLOCK_SETTINGS):
      block = await self.read_block(name, start, count, fallback)
      if block:
        blocks[name] = block
    log.info("bms.read_all.done", duration_s=round(time.monotonic() - started, 2), blocks=list(blocks))
    return blocks


async def scan() -> tuple[str, str | None]:
  """Scan for a Daly-looking BLE device. Raises BmsUnreachableError if none found."""
  started = time.monotonic()
  devices: list[BLEDevice] = await BleakScanner.discover(timeout=settings.BMS_SCAN_TIMEOUT)
  duration_s = round(time.monotonic() - started, 2)
  candidates = [d for d in devices if looks_like_daly(d.name)]
  if not candidates:
    log.warning("bms.scan.no_match", duration_s=duration_s, devices_seen=len(devices))
    raise BmsUnreachableError("no Daly BMS found during Bluetooth scan; make sure it is powered and no other app is connected to it")
  if len(candidates) > 1:
    log.warning("bms.scan.multiple_candidates", candidates=[f"{d.name} ({d.address})" for d in candidates])
  device = candidates[0]
  log.info("bms.scan.found", device_name=device.name, device_address=device.address, duration_s=duration_s)
  return device.address, device.name
