"""Connect to a Daly BMS over Bluetooth LE, auto-detect the device, and print all values.

Tries the classic Daly UART protocol (via the dalybms library) first; newer Daly
BLE boards (like this one) instead speak a Modbus-style protocol on the same
fff0 service, which is handled by DalyModbusBLE below.
"""

import asyncio
import json
import logging
import struct
import sys
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner
from dalybms import DalyBMSBluetooth
from dalybms.daly_bms import DalyBMS

# Daly BMS BLE UART service characteristics
NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"

SCAN_TIMEOUT = 10.0
CACHED_CONNECT_TIMEOUT = 15.0
RESPONSE_TIMEOUT = 5.0

# on macOS this is a CoreBluetooth UUID rather than a MAC address, but it is
# stable per device and lets us skip the full scan on subsequent runs
CACHE_FILE = Path(__file__).parent / ".daly_bms_cache.json"

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("golfbil")
log.setLevel(logging.INFO)


# --- classic protocol (dalybms library, patched for macOS + command-code fixes) ---

class DalyClassicBLE(DalyBMSBluetooth):
    """DalyBMSBluetooth with macOS-compatible connect/write (UUIDs instead of
    BlueZ handle numbers) and corrected command codes for 0x92/0x96/0x97/0x98."""

    async def connect(self, device):
        self.client = BleakClient(device)
        await self.client.connect()
        await self.client.start_notify(NOTIFY_UUID, self._notification_callback)

    async def _async_char_write(self, command, value):
        char = self.client.services.get_characteristic(WRITE_UUID)
        use_response = "write-without-response" not in char.properties
        await self.client.write_gatt_char(char, value, response=use_response)
        try:
            return await asyncio.wait_for(
                self.response_cache[command]["future"], RESPONSE_TIMEOUT)
        except asyncio.TimeoutError:
            self.logger.warning("Timeout while waiting for %s response", command)
            return False

    async def get_status(self):
        response_data = await self._read_request("94")
        if not response_data:
            return False
        return DalyBMS.get_status(self, response_data=response_data)

    async def get_soc(self):
        response_data = await self._read_request("90")
        if not response_data:
            return False
        return DalyBMS.get_soc(self, response_data=response_data)

    async def get_cell_voltage_range(self):
        response_data = await self._read_request("91")
        if not response_data:
            return False
        return DalyBMS.get_cell_voltage_range(self, response_data=response_data)

    async def get_mosfet_status(self):
        response_data = await self._read_request("93")
        if not response_data:
            return False
        return DalyBMS.get_mosfet_status(self, response_data=response_data)

    async def get_cell_voltages(self):
        if not self.status:
            return False
        # via Bluetooth the BMS always sends 16 frames of 3 cells each
        response_data = await self._read_request("95", max_responses=16)
        if not response_data:
            return False
        return DalyBMS.get_cell_voltages(self, response_data=response_data)

    async def get_temperature_range(self):
        response_data = await self._read_request("92")
        if not response_data:
            return False
        return DalyBMS.get_temperature_range(self, response_data=response_data)

    async def get_temperatures(self):
        if not self.status:
            await self.get_status()
        response_data = await self._read_request("96", max_responses=3)
        if not response_data:
            return False
        return DalyBMS.get_temperatures(self, response_data=response_data)

    async def get_balancing_status(self):
        response_data = await self._read_request("97")
        if not response_data or not self.status:
            return False
        bits = bin(int.from_bytes(response_data, byteorder="big"))[2:].zfill(48)
        return {cell: bool(int(bits[-cell])) for cell in range(1, self.status["cells"] + 1)}

    async def get_errors(self):
        response_data = await self._read_request("98")
        if not response_data:
            return False
        return DalyBMS.get_errors(self, response_data=response_data)

    async def read_all(self):
        # status first: cell/sensor counts are needed to parse voltages & temperatures
        status = await self.get_status()
        if not status:
            return None
        return {
            "Status (0x94)": status,
            "SOC / pack (0x90)": await self.get_soc(),
            "Cell voltage range (0x91)": await self.get_cell_voltage_range(),
            "Temperature range (0x92)": await self.get_temperature_range(),
            "MOSFET status (0x93)": await self.get_mosfet_status(),
            "Cell voltages (0x95)": await self.get_cell_voltages(),
            "Temperatures (0x96)": await self.get_temperatures(),
            "Balancing (0x97)": await self.get_balancing_status(),
            "Errors (0x98)": await self.get_errors(),
        }


# --- Modbus-style protocol (newer Daly BLE boards) ---

MODE_NAMES = {0: "idle", 1: "charging", 2: "discharging"}
UNUSED = 0xFFFF

# register blocks this BMS answers (start, count, fallback count)
BLOCK_MAIN = ("main_0x0000", 0x0000, 0x50, 0x3E)
BLOCK_INFO = ("info_0x0050", 0x0050, 0x20, None)
BLOCK_SETTINGS = ("settings_0x0080", 0x0080, 0x10, None)


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


class DalyModbusBLE:
    def __init__(self, client: BleakClient):
        self.client = client
        self._buffer = bytearray()
        self._future = None

    async def start(self):
        await self.client.start_notify(NOTIFY_UUID, self._on_notify)

    def _on_notify(self, sender, data):
        self._buffer.extend(data)
        if len(self._buffer) < 3:
            return
        expected = 3 + self._buffer[2] + 2  # header + payload + crc
        if len(self._buffer) >= expected and self._future and not self._future.done():
            self._future.set_result(bytes(self._buffer[:expected]))

    async def read_registers(self, start: int, count: int):
        """Read `count` 16-bit registers from `start`; returns (frame_hex, registers)."""
        self._buffer.clear()
        self._future = asyncio.get_running_loop().create_future()
        await self.client.write_gatt_char(
            WRITE_UUID, modbus_request(start, count), response=True)
        frame = await asyncio.wait_for(self._future, RESPONSE_TIMEOUT)

        if frame[0] != 0xD2 or frame[1] != 0x03:
            raise ValueError(f"unexpected frame header: {frame[:3].hex()}")
        crc = struct.unpack("<H", frame[-2:])[0]
        if crc != crc16_modbus(frame[:-2]):
            raise ValueError("CRC mismatch in BMS response")
        payload = frame[3:-2]
        return frame.hex(), list(struct.unpack(f">{len(payload) // 2}H", payload))

    async def read_block(self, name, start, count, fallback_count=None):
        try:
            frame_hex, regs = await self.read_registers(start, count)
        except (asyncio.TimeoutError, ValueError) as e:
            if fallback_count is None:
                log.warning("Block %s not available (%s)", name, e or "timeout")
                return None
            log.info("Block %s: count 0x%02x failed, retrying with 0x%02x",
                     name, count, fallback_count)
            count = fallback_count
            frame_hex, regs = await self.read_registers(start, count)
        return {
            "request": {"start": start, "count": count},
            "frame_hex": frame_hex,
            "registers": regs,
        }

    async def read_all(self):
        blocks = {}
        for name, start, count, fallback in (BLOCK_MAIN, BLOCK_INFO, BLOCK_SETTINGS):
            block = await self.read_block(name, start, count, fallback)
            if block:
                blocks[name] = block
        return blocks


def bitmask_to_cells(mask: int) -> list[int]:
    return [i + 1 for i in range(16) if mask & (1 << i)]


def decode_blocks(blocks: dict) -> dict:
    """Human-readable view; every raw register is preserved in the blocks dict."""
    regs = blocks["main_0x0000"]["registers"]
    cell_count = regs[49]
    sensor_count = regs[50]
    voltage = regs[40] / 10
    current = (regs[41] - 30000) / 10

    decoded = {
        "Pack": {
            "total_voltage_v": voltage,
            "current_a": current,
            "power_w": round(voltage * current, 1),
            "soc_percent": regs[42] / 10,
            "remaining_capacity_ah": regs[48] / 10,
            "mode": MODE_NAMES.get(regs[47], regs[47]),
            "cycles": regs[51],
        },
        "Cell voltages": {
            f"cell_{i + 1}_v": regs[i] / 1000 for i in range(cell_count)
        },
        "Cell voltage stats": {
            "max_v": regs[43] / 1000,
            "min_v": regs[44] / 1000,
            "average_v": regs[55] / 1000,
            "delta_v": regs[56] / 1000,
        },
        "Temperatures": {
            f"sensor_{i + 1}_c": regs[32 + i] - 40 for i in range(sensor_count)
        } | {
            "max_c": regs[45] - 40,
            "min_c": regs[46] - 40,
        },
        "Status": {
            "cells": cell_count,
            "temperature_sensors": sensor_count,
            "balancer_active": bool(regs[52]),
            "charging_mosfet": bool(regs[53]),
            "discharging_mosfet": bool(regs[54]),
        },
        "Alarms": {
            f"alarm_register_{i}": f"0x{regs[58 + i]:04x}" for i in range(4)
        } if any(regs[58:62]) else "none",
    }

    if len(regs) > 66:  # extended part of the main block
        balancing = {
            "balance_current_a": (regs[64] - 30000) / 10,
            "balancing_cells": bitmask_to_cells(regs[65]),
        }
        if regs[66] != UNUSED:
            balancing["mosfet_temperature_c"] = regs[66] - 40
        if len(regs) > 67 and regs[67] != UNUSED:
            balancing["board_temperature_c"] = regs[67] - 40
        decoded["Balancing"] = balancing

    if info := blocks.get("info_0x0050"):
        raw = struct.pack(f">{len(info['registers'])}H", *info["registers"])
        model = raw.strip(b"\x00\xff").decode("ascii", errors="replace")
        decoded["Device info"] = {"model": model}

    if settings := blocks.get("settings_0x0080"):
        sregs = settings["registers"]
        decoded["Settings"] = {
            "rated_capacity_ah": sregs[0] / 10,
            "cell_count": sregs[3],
            "raw": " ".join(f"{r:04x}" for r in sregs),
        }

    return decoded


# --- discovery & output ---

def looks_like_daly(name: str | None) -> bool:
    if not name:
        return False
    upper = name.upper()
    return upper.startswith("DL-") or "DALY" in upper


def load_cached_address():
    try:
        cache = json.loads(CACHE_FILE.read_text())
        return cache["address"], cache.get("name", "?")
    except (OSError, ValueError, KeyError):
        return None, None


def save_cached_address(device):
    try:
        CACHE_FILE.write_text(json.dumps({"address": device.address, "name": device.name}))
    except OSError as e:
        log.warning("Could not write address cache: %s", e)


async def find_bms():
    log.info("Scanning for Bluetooth LE devices (%.0fs)...", SCAN_TIMEOUT)
    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT)
    named = [d for d in devices if d.name]
    log.info("Found %d devices (%d with names)", len(devices), len(named))

    candidates = [d for d in named if looks_like_daly(d.name)]
    if not candidates:
        print("\nNo Daly BMS found. Devices seen:")
        for d in sorted(named, key=lambda d: d.name):
            print(f"  {d.address}  {d.name}")
        print("\nMake sure the BMS is powered and no other app (e.g. the Daly phone app) is connected to it.")
        return None

    if len(candidates) > 1:
        log.warning("Multiple Daly candidates found, using the first: %s",
                    ", ".join(f"{d.name} ({d.address})" for d in candidates))
    device = candidates[0]
    log.info("Detected Daly BMS: %s (%s)", device.name, device.address)
    save_cached_address(device)
    return device


def print_section(title, data):
    print(f"\n=== {title} ===")
    if data is False or data is None:
        print("  <no response>")
    elif isinstance(data, dict):
        for key, value in data.items():
            print(f"  {key}: {value}")
    elif isinstance(data, list):
        for item in data or ["none"]:
            print(f"  {item}")
    else:
        print(f"  {data}")


async def connect_bms() -> DalyClassicBLE:
    bms = DalyClassicBLE(request_retries=1)

    # a cached address lets CoreBluetooth connect directly, skipping the scan
    address, name = load_cached_address()
    if address:
        log.info("Connecting to cached BMS %s (%s)...", name, address)
        try:
            await asyncio.wait_for(bms.connect(address), CACHED_CONNECT_TIMEOUT)
            return bms
        except (Exception, asyncio.TimeoutError) as e:
            log.info("Cached connect failed (%s), falling back to scan", e or type(e).__name__)

    device = await find_bms()
    if device is None:
        sys.exit(1)
    log.info("Connecting to %s...", device.name)
    await bms.connect(device)
    return bms


READINGS_DIR = Path(__file__).parent / "readings"


def save_reading(reading: dict) -> Path:
    READINGS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().astimezone()
    path = READINGS_DIR / f"{stamp.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    reading = {"timestamp": stamp.isoformat(), **reading}
    path.write_text(json.dumps(reading, indent=2))
    return path


async def main():
    bms = await connect_bms()
    log.info("Connected, trying classic Daly protocol...")

    address, name = load_cached_address()
    reading = {"device": {"name": name, "address": address}}
    try:
        values = await bms.read_all()
        if values is not None:
            reading["protocol"] = "daly-classic"
            reading["decoded"] = values
        else:
            log.info("No response to classic protocol, using Modbus protocol instead")
            await bms.client.stop_notify(NOTIFY_UUID)
            modbus = DalyModbusBLE(bms.client)
            await modbus.start()
            blocks = await modbus.read_all()
            values = decode_blocks(blocks)
            reading["protocol"] = "daly-modbus-ble"
            reading["raw_blocks"] = blocks
            reading["decoded"] = values

        for title, data in values.items():
            print_section(title, data)

        path = save_reading(reading)
        print(f"\nSaved to {path}")
    finally:
        await bms.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
