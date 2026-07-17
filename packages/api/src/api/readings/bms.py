"""Bluetooth LE client for Daly BMS boards speaking the Modbus-style protocol
on the fff0 UART service.

All bleak I/O is confined to this module; `capture_reading` is the single entry
point the endpoints call (and tests mock).
"""

import asyncio
import logging
import struct
from dataclasses import dataclass
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from api.readings.decode import MAIN_BLOCK, DecodedReading, decode_blocks
from api.settings import settings

log = logging.getLogger(__name__)

NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"

PROTOCOL = "daly-modbus-ble"

# register blocks the BMS answers (name, start, count, fallback count)
BLOCK_MAIN = (MAIN_BLOCK, 0x0000, 0x50, 0x3E)
BLOCK_INFO = ("info_0x0050", 0x0050, 0x20, None)
BLOCK_SETTINGS = ("settings_0x0080", 0x0080, 0x10, None)

# Only one BLE connection to the BMS can be open at a time.
capture_lock = asyncio.Lock()

# Discovered device, cached in-process so only the first capture pays for a
# scan. Not used when settings.BMS_ADDRESS is set.
_discovered: tuple[str, str | None] | None = None


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
  def __init__(self, client: BleakClient):
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
    try:
      frame_hex, regs = await self.read_registers(start, count)
    except (TimeoutError, ValueError) as e:
      if fallback_count is None:
        log.warning("Block %s not available (%s)", name, e or "timeout")
        return None
      log.info("Block %s: count 0x%02x failed, retrying with 0x%02x", name, count, fallback_count)
      count = fallback_count
      frame_hex, regs = await self.read_registers(start, count)
    return {
      "request": {"start": start, "count": count},
      "frame_hex": frame_hex,
      "registers": regs,
    }

  async def read_all(self) -> dict[str, Any]:
    blocks = {}
    for name, start, count, fallback in (BLOCK_MAIN, BLOCK_INFO, BLOCK_SETTINGS):
      block = await self.read_block(name, start, count, fallback)
      if block:
        blocks[name] = block
    return blocks


async def _scan() -> tuple[str, str | None]:
  devices = await BleakScanner.discover(timeout=settings.BMS_SCAN_TIMEOUT)
  candidates = [d for d in devices if looks_like_daly(d.name)]
  if not candidates:
    raise BmsUnreachableError("no Daly BMS found during Bluetooth scan; make sure it is powered and no other app is connected to it")
  if len(candidates) > 1:
    log.warning("Multiple Daly candidates found, using the first: %s", ", ".join(f"{d.name} ({d.address})" for d in candidates))
  device = candidates[0]
  log.info("Detected Daly BMS: %s (%s)", device.name, device.address)
  return device.address, device.name


async def _capture_from(address: str, name: str | None) -> CaptureResult:
  try:
    async with BleakClient(address, timeout=settings.BMS_CONNECT_TIMEOUT) as client:
      bms = DalyModbusBLE(client)
      await bms.start()
      blocks = await bms.read_all()
  except (BleakError, TimeoutError, OSError, ValueError) as e:
    raise BmsUnreachableError(str(e) or type(e).__name__) from e
  return CaptureResult(device_name=name, device_address=address, blocks=blocks, decoded=decode_blocks(blocks))


async def capture_reading() -> CaptureResult:
  """Resolve the BMS address (settings > cached discovery > scan), connect, and
  read all register blocks. Raises BmsUnreachableError on any failure."""
  global _discovered

  if settings.BMS_ADDRESS:
    return await _capture_from(settings.BMS_ADDRESS, None)

  if _discovered is not None:
    address, name = _discovered
    try:
      return await _capture_from(address, name)
    except BmsUnreachableError as e:
      log.info("Cached BMS %s unreachable (%s), rescanning", address, e)
      _discovered = None

  address, name = await _scan()
  _discovered = (address, name)
  return await _capture_from(address, name)
