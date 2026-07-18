"""Keeps one persistent BLE connection to the BMS alive for as long as it's in
range, reconnecting with backoff when it drops. Serves both a 60s background
poll (saved to history) and on-demand reads triggered by API requests.

The cart is only in Bluetooth range of this host when idle/charging near it —
there is no separate "is the cart idle" check; reconnect-with-backoff and a
no-op while unreachable naturally produces exactly that behavior.

Outside of that, the connection is also deliberately dropped during a nightly
quiet-hours window (BMS_QUIET_HOURS_*, local time) so the BMS isn't held open
around the clock; the reconnect loop stands down for the window and a
dedicated loop disconnects if the window starts while still connected.
"""

import asyncio
import contextlib
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from bleak import BleakClient
from bleak.exc import BleakError

from api.common.db.engine import AsyncSessionMaker
from api.readings import bms
from api.readings.bms import BmsUnreachableError, CaptureResult, DalyModbusBLE
from api.readings.decode import decode_blocks
from api.readings.persist import persist_reading
from api.settings import settings

log = structlog.get_logger()


class BmsConnection:
  def __init__(self) -> None:
    self._client: BleakClient | None = None
    self._daly: DalyModbusBLE | None = None
    self._address: str | None = None
    self._io_lock = asyncio.Lock()
    self._disconnected_event = asyncio.Event()
    self._disconnected_event.set()
    self._sessionmaker: AsyncSessionMaker | None = None
    self._reconnect_task: asyncio.Task[None] | None = None
    self._poll_task: asyncio.Task[None] | None = None
    self._quiet_hours_task: asyncio.Task[None] | None = None

  @property
  def is_connected(self) -> bool:
    return self._client is not None and self._client.is_connected

  def _on_disconnected(self, _client: BleakClient) -> None:
    log.warning("bms.connection.dropped", address=self._address)
    self._disconnected_event.set()

  async def start(self, sessionmaker: AsyncSessionMaker) -> None:
    self._sessionmaker = sessionmaker
    self._reconnect_task = asyncio.create_task(self._reconnect_loop(), name="bms-reconnect")
    self._poll_task = asyncio.create_task(self._poll_loop(), name="bms-poll")
    self._quiet_hours_task = asyncio.create_task(self._quiet_hours_loop(), name="bms-quiet-hours")

  async def stop(self) -> None:
    tasks = (self._poll_task, self._reconnect_task, self._quiet_hours_task)
    for task in tasks:
      if task:
        task.cancel()
    for task in tasks:
      if task:
        with contextlib.suppress(asyncio.CancelledError):
          await task
    if self._client is not None and self._client.is_connected:
      await self._client.disconnect()

  def _in_quiet_hours(self) -> bool:
    hour = datetime.now(ZoneInfo(settings.BMS_QUIET_HOURS_TZ)).hour
    return settings.BMS_QUIET_HOURS_START_H <= hour < settings.BMS_QUIET_HOURS_END_H

  async def read_now(self) -> CaptureResult:
    """Used by the on-demand endpoint. Tries to connect immediately if not
    already connected — doesn't wait for the reconnect loop's backoff."""
    if not self.is_connected:
      await self._connect()
    async with self._io_lock:
      assert self._daly is not None
      try:
        blocks = await self._daly.read_all()
      except (BleakError, TimeoutError, OSError, ValueError) as e:
        log.warning("bms.read.failed", address=self._address, error=str(e) or type(e).__name__)
        await self._mark_disconnected()
        raise BmsUnreachableError(str(e) or type(e).__name__) from e
    return CaptureResult(device_name=None, device_address=self._address or "", blocks=blocks, decoded=decode_blocks(blocks))

  async def _mark_disconnected(self) -> None:
    """Force is_connected to False and best-effort disconnect the stale client.
    Don't rely solely on bleak's own is_connected tracking — a read can fail
    for reasons other than an actual link drop (a bad CRC, a malformed frame),
    and without this the next read_now()/reconnect loop would keep reusing the
    same broken connection instead of establishing a fresh one."""
    client, self._client, self._daly = self._client, None, None
    self._disconnected_event.set()
    if client is not None and client.is_connected:
      with contextlib.suppress(BleakError, TimeoutError, OSError):
        await client.disconnect()

  async def _resolve_address(self) -> str:
    if settings.BMS_ADDRESS:
      return settings.BMS_ADDRESS
    if self._address:
      return self._address
    address, _name = await bms.scan()
    return address

  async def _connect(self) -> None:
    async with self._io_lock:
      if self.is_connected:
        return

      address = await self._resolve_address()
      last_error: Exception | None = None
      overall_started = time.monotonic()

      for attempt in range(1, settings.BMS_CONNECT_ATTEMPTS + 1):
        started = time.monotonic()
        client = BleakClient(address, disconnected_callback=self._on_disconnected, services=[bms.SERVICE_UUID], timeout=settings.BMS_CONNECT_TIMEOUT)
        try:
          await client.connect()
          daly = DalyModbusBLE(client)
          await daly.start()
        except (BleakError, TimeoutError, OSError) as e:
          last_error = e
          log.warning(
            "bms.connect.attempt_failed",
            address=address,
            attempt=attempt,
            of=settings.BMS_CONNECT_ATTEMPTS,
            duration_s=round(time.monotonic() - started, 2),
            error=str(e) or type(e).__name__,
          )
          if client.is_connected:
            # connect() succeeded but subscribing to notifications failed —
            # don't leak a half-open connection.
            with contextlib.suppress(BleakError, TimeoutError, OSError):
              await client.disconnect()
          continue
        self._client, self._daly, self._address = client, daly, address
        self._disconnected_event.clear()
        log.info("bms.connection.established", address=address, attempt=attempt, duration_s=round(time.monotonic() - started, 2))
        return

      total_s = round(time.monotonic() - overall_started, 2)
      if isinstance(last_error, TimeoutError):
        message = f"BLE connect timed out after {settings.BMS_CONNECT_ATTEMPTS} attempt(s) ({total_s}s total)"
      else:
        message = str(last_error) or type(last_error).__name__
      log.warning("bms.connect.failed", address=address, attempts=settings.BMS_CONNECT_ATTEMPTS, error=message)
      raise BmsUnreachableError(message)

  async def _reconnect_loop(self) -> None:
    while True:
      await self._disconnected_event.wait()
      try:
        if self._in_quiet_hours():
          await asyncio.sleep(settings.BMS_QUIET_HOURS_CHECK_S)
          continue
        await self._connect()
      except BmsUnreachableError as e:
        log.info("bms.reconnect.retry_scheduled", error=str(e), backoff_s=settings.BMS_RECONNECT_BACKOFF_S)
        await asyncio.sleep(settings.BMS_RECONNECT_BACKOFF_S)
      except Exception:
        log.exception("bms.reconnect_loop.unexpected_error")
        await asyncio.sleep(settings.BMS_RECONNECT_BACKOFF_S)

  async def _quiet_hours_loop(self) -> None:
    """Proactively drops an already-open connection once the quiet-hours
    window starts; the reconnect loop's own check keeps it down from there."""
    while True:
      await asyncio.sleep(settings.BMS_QUIET_HOURS_CHECK_S)
      try:
        if self._in_quiet_hours() and self.is_connected:
          log.info("bms.quiet_hours.disconnecting", address=self._address)
          await self._mark_disconnected()
      except Exception:
        log.exception("bms.quiet_hours_loop.unexpected_error")

  async def _poll_loop(self) -> None:
    while True:
      await asyncio.sleep(settings.BMS_POLL_INTERVAL_S)
      try:
        await self._poll_once()
      except Exception:
        log.exception("bms.poll_loop.unexpected_error")

  async def _poll_once(self) -> None:
    if not self.is_connected:
      return
    try:
      result = await self.read_now()
    except BmsUnreachableError as e:
      log.warning("bms.poll.failed", error=str(e))
      return

    assert self._sessionmaker is not None
    async with self._sessionmaker() as session:
      await persist_reading(session, result)
      await session.commit()
    log.info("bms.poll.saved", address=result.device_address)


connection = BmsConnection()
