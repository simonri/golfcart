import json
import tempfile
from collections.abc import AsyncIterator
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from api.common.db.engine import AsyncSessionMaker, create_async_engine, create_async_sessionmaker
from api.models.base import Model
from api.readings.bms import BmsUnreachableError, CaptureResult
from api.readings.connection import BmsConnection
from api.readings.decode import decode_blocks
from api.readings.repository import ReadingRepository
from api.tests.fixtures.database import SaveFixture
from api.tests.fixtures.random_objects import create_reading
from bleak.exc import BleakError
from httpx import AsyncClient
from pytest_mock import MockerFixture

SAMPLE_BLOCKS_PATH = Path(__file__).parent / "fixtures" / "data" / "daly_sample_blocks.json"


@pytest.fixture
def sample_blocks() -> dict[str, Any]:
  return json.loads(SAMPLE_BLOCKS_PATH.read_text())


@pytest.fixture
def sample_capture(sample_blocks: dict[str, Any]) -> CaptureResult:
  return CaptureResult(
    device_name="DL-411905019B59",
    device_address="AA:BB:CC:DD:EE:FF",
    blocks=sample_blocks,
    decoded=decode_blocks(sample_blocks),
  )


@pytest.fixture
def connection() -> BmsConnection:
  """A fresh, unconnected BmsConnection — isolated from the app's singleton."""
  return BmsConnection()


@pytest_asyncio.fixture
async def isolated_sessionmaker() -> AsyncIterator[AsyncSessionMaker]:
  """A standalone sqlite-backed sessionmaker, isolated from the shared test
  DB/transaction, for exercising code paths that commit their own session
  (background poll persistence) without disturbing other tests' rollback-based
  isolation."""
  db_path = Path(tempfile.gettempdir()) / f"bessel_test_poll_{uuid4().hex}.db"
  engine = create_async_engine(dsn=f"sqlite+aiosqlite:///{db_path}")
  async with engine.begin() as conn:
    await conn.run_sync(Model.metadata.create_all)
  try:
    yield create_async_sessionmaker(engine)
  finally:
    await engine.dispose()
    db_path.unlink(missing_ok=True)


class TestDecodeBlocks:
  def test_decodes_sample(self, sample_blocks: dict[str, Any]) -> None:
    decoded = decode_blocks(sample_blocks)

    assert decoded.voltage_v == 56.6
    assert decoded.current_a == 17.6
    assert decoded.power_w == 996.2
    assert decoded.soc_percent == 42.6
    assert decoded.remaining_capacity_ah == 21.3
    assert decoded.rated_capacity_ah == 50.0
    assert decoded.mode == "charging"
    assert decoded.cycles == 2

    assert decoded.cell_count == 14
    assert len(decoded.cell_voltages) == 14
    assert decoded.cell_voltages[0] == 3.981
    assert decoded.cell_voltage_max_v == 4.073
    assert decoded.cell_voltage_min_v == 3.981
    assert decoded.cell_voltage_avg_v == 4.051
    assert decoded.cell_voltage_delta_v == 0.092

    assert decoded.temperature_sensor_count == 2
    assert decoded.temperatures == [33, 33]
    assert decoded.temperature_max_c == 33
    assert decoded.temperature_min_c == 33

    assert decoded.balancer_active is True
    assert decoded.charging_mosfet is True
    assert decoded.discharging_mosfet is True
    assert decoded.alarms is None
    assert decoded.alarm_messages is None

    assert decoded.balancing is not None
    assert decoded.balancing.balance_current_a == 0.0
    assert decoded.balancing.balancing_cells == [1, 2, 3]
    assert decoded.balancing.mosfet_temperature_c == 34
    assert decoded.balancing.board_temperature_c is None

    assert decoded.device_model == "226KF270201240"

  def test_decodes_alarm_registers(self, sample_blocks: dict[str, Any]) -> None:
    blocks = deepcopy(sample_blocks)
    blocks["main_0x0000"]["registers"][58] = 0x0102

    decoded = decode_blocks(blocks)

    assert decoded.alarms == {
      "alarm_register_0": "0x0102",
      "alarm_register_1": "0x0000",
      "alarm_register_2": "0x0000",
      "alarm_register_3": "0x0000",
    }
    assert decoded.alarm_messages == [
      "Critical: Cell voltage too high",
      "Warning: Charging temperature too high",
    ]

  def test_decodes_alarm_messages_for_high_soc_reading(self, sample_blocks: dict[str, Any]) -> None:
    # Matches a real capture at 99.8% SOC: Alarm1=0x0011, others clear.
    blocks = deepcopy(sample_blocks)
    blocks["main_0x0000"]["registers"][58] = 0x0011

    decoded = decode_blocks(blocks)

    assert decoded.alarm_messages == [
      "Warning: Cell voltage too high",
      "Warning: Total voltage too high",
    ]

  def test_reserved_alarm_bit_is_labeled_reserved(self, sample_blocks: dict[str, Any]) -> None:
    blocks = deepcopy(sample_blocks)
    blocks["main_0x0000"]["registers"][59] = 0x1000

    decoded = decode_blocks(blocks)

    assert decoded.alarm_messages == ["Reserved"]

  def test_alarm4_bits_are_unused(self, sample_blocks: dict[str, Any]) -> None:
    # Alarm4 (register 61) has no assigned bit meanings; a set bit there still
    # counts toward has_alarms/raw alarms, but yields no readable message.
    blocks = deepcopy(sample_blocks)
    blocks["main_0x0000"]["registers"][61] = 0xFFFF

    decoded = decode_blocks(blocks)

    assert decoded.alarms is not None
    assert decoded.alarm_messages == []

  def test_short_main_block_has_no_balancing(self, sample_blocks: dict[str, Any]) -> None:
    blocks = deepcopy(sample_blocks)
    blocks["main_0x0000"]["registers"] = blocks["main_0x0000"]["registers"][:62]

    decoded = decode_blocks(blocks)

    assert decoded.balancing is None
    assert decoded.voltage_v == 56.6

  def test_missing_optional_blocks(self, sample_blocks: dict[str, Any]) -> None:
    blocks = {"main_0x0000": sample_blocks["main_0x0000"]}

    decoded = decode_blocks(blocks)

    assert decoded.device_model is None
    assert decoded.rated_capacity_ah is None


def _mock_bleak_client(mocker: MockerFixture, connect_side_effect: Any = None) -> Any:
  """A fake BleakClient: tracks connected state, supports connect()/disconnect(),
  and is_connected reflects it — enough for BmsConnection's own logic, without
  simulating the real modbus wire protocol (that's covered by TestDecodeBlocks)."""
  fake = mocker.MagicMock()
  fake.is_connected = False

  async def connect() -> None:
    if connect_side_effect is not None:
      raise connect_side_effect
    fake.is_connected = True

  async def disconnect() -> None:
    fake.is_connected = False

  fake.connect = mocker.AsyncMock(side_effect=connect)
  fake.disconnect = mocker.AsyncMock(side_effect=disconnect)
  return fake


def _mock_daly(mocker: MockerFixture, blocks: dict[str, Any], read_side_effect: Any = None) -> Any:
  fake = mocker.MagicMock()
  fake.start = mocker.AsyncMock()
  fake.read_all = mocker.AsyncMock(side_effect=read_side_effect or (lambda: blocks))
  return fake


class TestBmsConnection:
  @pytest.mark.asyncio
  async def test_read_now_connects_once_and_reuses(self, mocker: MockerFixture, connection: BmsConnection, sample_blocks: dict[str, Any]) -> None:
    mocker.patch("api.readings.connection.bms.scan", return_value=("AA:BB:CC:DD:EE:FF", "DL-TEST"))
    fake_client = _mock_bleak_client(mocker)
    mocker.patch("api.readings.connection.BleakClient", return_value=fake_client)
    fake_daly = _mock_daly(mocker, sample_blocks)
    mocker.patch("api.readings.connection.DalyModbusBLE", return_value=fake_daly)

    result1 = await connection.read_now()
    result2 = await connection.read_now()

    assert fake_client.connect.await_count == 1
    assert fake_daly.read_all.await_count == 2
    assert result1.blocks == sample_blocks
    assert result2.device_address == "AA:BB:CC:DD:EE:FF"

  @pytest.mark.asyncio
  async def test_connect_retries_then_succeeds(self, mocker: MockerFixture, connection: BmsConnection, sample_blocks: dict[str, Any]) -> None:
    mocker.patch("api.readings.connection.bms.scan", return_value=("AA:BB:CC:DD:EE:FF", "DL-TEST"))
    failing_client = _mock_bleak_client(mocker, connect_side_effect=TimeoutError())
    ok_client = _mock_bleak_client(mocker)
    mocker.patch("api.readings.connection.BleakClient", side_effect=[failing_client, ok_client])
    fake_daly = _mock_daly(mocker, sample_blocks)
    mocker.patch("api.readings.connection.DalyModbusBLE", return_value=fake_daly)

    result = await connection.read_now()

    assert failing_client.connect.await_count == 1
    assert ok_client.connect.await_count == 1
    assert result.blocks == sample_blocks

  @pytest.mark.asyncio
  async def test_connect_exhausts_attempts_raises_clear_message(self, mocker: MockerFixture, connection: BmsConnection) -> None:
    mocker.patch("api.readings.connection.bms.scan", return_value=("AA:BB:CC:DD:EE:FF", "DL-TEST"))
    mocker.patch(
      "api.readings.connection.BleakClient",
      side_effect=lambda *a, **k: _mock_bleak_client(mocker, connect_side_effect=TimeoutError()),
    )

    with pytest.raises(BmsUnreachableError, match="BLE connect timed out after 2 attempt"):
      await connection.read_now()

  @pytest.mark.asyncio
  async def test_read_failure_marks_disconnected_then_reconnects(self, mocker: MockerFixture, connection: BmsConnection, sample_blocks: dict[str, Any]) -> None:
    mocker.patch("api.readings.connection.bms.scan", return_value=("AA:BB:CC:DD:EE:FF", "DL-TEST"))
    client1 = _mock_bleak_client(mocker)
    client2 = _mock_bleak_client(mocker)
    mocker.patch("api.readings.connection.BleakClient", side_effect=[client1, client2])
    daly1 = _mock_daly(mocker, sample_blocks, read_side_effect=BleakError("link lost"))
    daly2 = _mock_daly(mocker, sample_blocks)
    mocker.patch("api.readings.connection.DalyModbusBLE", side_effect=[daly1, daly2])

    with pytest.raises(BmsUnreachableError):
      await connection.read_now()
    assert connection.is_connected is False

    result = await connection.read_now()
    assert result.blocks == sample_blocks
    assert client2.connect.await_count == 1

  @pytest.mark.asyncio
  async def test_poll_once_persists_a_reading(
    self,
    mocker: MockerFixture,
    connection: BmsConnection,
    sample_blocks: dict[str, Any],
    isolated_sessionmaker: AsyncSessionMaker,
  ) -> None:
    mocker.patch("api.readings.connection.bms.scan", return_value=("AA:BB:CC:DD:EE:FF", "DL-TEST"))
    mocker.patch("api.readings.connection.BleakClient", return_value=_mock_bleak_client(mocker))
    mocker.patch("api.readings.connection.DalyModbusBLE", return_value=_mock_daly(mocker, sample_blocks))
    connection._sessionmaker = isolated_sessionmaker
    await connection._connect()  # _poll_once only reads if already connected, by design

    await connection._poll_once()

    async with isolated_sessionmaker() as session:
      latest = await ReadingRepository.from_session(session).get_latest()
    assert latest is not None
    assert latest.voltage_v == 56.6

  @pytest.mark.asyncio
  async def test_poll_once_skips_when_not_connected(self, connection: BmsConnection, isolated_sessionmaker: AsyncSessionMaker) -> None:
    connection._sessionmaker = isolated_sessionmaker

    await connection._poll_once()  # no BleakClient/DalyModbusBLE mocked — must not attempt to connect

    async with isolated_sessionmaker() as session:
      latest = await ReadingRepository.from_session(session).get_latest()
    assert latest is None


class TestCaptureReading:
  @pytest.mark.asyncio
  async def test_capture_persists_and_returns_reading(self, client: AsyncClient, mocker: MockerFixture, sample_capture: CaptureResult) -> None:
    mocker.patch("api.readings.endpoints.connection.read_now", return_value=sample_capture)

    resp = await client.post("/v1/readings")
    assert resp.status_code == 201
    body = resp.json()
    assert body["device_name"] == "DL-411905019B59"
    assert body["device_model"] == "226KF270201240"
    assert body["protocol"] == "daly-modbus-ble"
    assert body["voltage_v"] == 56.6
    assert body["soc_percent"] == 42.6
    assert body["mode"] == "charging"
    assert len(body["cell_voltages"]) == 14
    assert body["balancing"]["balancing_cells"] == [1, 2, 3]
    assert body["has_alarms"] is False
    assert body["alarms"] is None
    assert "raw" not in body

    listed = (await client.get("/v1/readings")).json()
    assert listed["pagination"]["total_count"] == 1
    assert listed["items"][0]["id"] == body["id"]


class TestCaptureErrors:
  @pytest.mark.asyncio
  async def test_unreachable_bms_returns_503(self, client: AsyncClient, mocker: MockerFixture) -> None:
    mocker.patch("api.readings.endpoints.connection.read_now", side_effect=BmsUnreachableError("no Daly BMS found during Bluetooth scan"))

    resp = await client.post("/v1/readings")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "ServiceUnavailableError"
    assert "no Daly BMS found" in body["detail"]

    listed = (await client.get("/v1/readings")).json()
    assert listed["pagination"]["total_count"] == 0


class TestListReadings:
  @pytest.mark.asyncio
  async def test_sorted_newest_first(self, client: AsyncClient, save_fixture: SaveFixture) -> None:
    for hour in (10, 12, 11):
      await save_fixture(create_reading(created_at=datetime(2026, 7, 17, hour, tzinfo=UTC), voltage_v=50.0 + hour))

    body = (await client.get("/v1/readings")).json()
    assert [item["voltage_v"] for item in body["items"]] == [62.0, 61.0, 60.0]

  @pytest.mark.asyncio
  async def test_pagination(self, client: AsyncClient, save_fixture: SaveFixture) -> None:
    for hour in (10, 11, 12):
      await save_fixture(create_reading(created_at=datetime(2026, 7, 17, hour, tzinfo=UTC)))

    body = (await client.get("/v1/readings", params={"limit": 2, "page": 2})).json()
    assert len(body["items"]) == 1
    assert body["pagination"]["total_count"] == 3
    assert body["pagination"]["max_page"] == 2

  @pytest.mark.asyncio
  async def test_time_range_filters(self, client: AsyncClient, save_fixture: SaveFixture) -> None:
    for hour in (10, 11, 12):
      await save_fixture(create_reading(created_at=datetime(2026, 7, 17, hour, tzinfo=UTC), voltage_v=50.0 + hour))

    after = int(datetime(2026, 7, 17, 11, tzinfo=UTC).timestamp())
    before = int(datetime(2026, 7, 17, 12, tzinfo=UTC).timestamp())

    body = (await client.get("/v1/readings", params={"created_after": after})).json()
    assert [item["voltage_v"] for item in body["items"]] == [62.0, 61.0]

    body = (await client.get("/v1/readings", params={"created_after": after, "created_before": before})).json()
    assert [item["voltage_v"] for item in body["items"]] == [61.0]

  @pytest.mark.asyncio
  async def test_has_alarms_filter(self, client: AsyncClient, save_fixture: SaveFixture) -> None:
    await save_fixture(create_reading(has_alarms=True, alarms={"alarm_register_0": "0x0001"}))
    await save_fixture(create_reading())
    await save_fixture(create_reading())

    body = (await client.get("/v1/readings", params={"has_alarms": True})).json()
    assert body["pagination"]["total_count"] == 1
    assert body["items"][0]["alarms"] == {"alarm_register_0": "0x0001"}


class TestLatestReading:
  @pytest.mark.asyncio
  async def test_no_readings_returns_404(self, client: AsyncClient) -> None:
    resp = await client.get("/v1/readings/latest")
    assert resp.status_code == 404

  @pytest.mark.asyncio
  async def test_returns_newest(self, client: AsyncClient, save_fixture: SaveFixture) -> None:
    await save_fixture(create_reading(created_at=datetime(2026, 7, 17, 10, tzinfo=UTC), voltage_v=60.0))
    await save_fixture(create_reading(created_at=datetime(2026, 7, 17, 12, tzinfo=UTC), voltage_v=62.0))

    resp = await client.get("/v1/readings/latest")
    assert resp.status_code == 200
    assert resp.json()["voltage_v"] == 62.0


class TestGetReading:
  @pytest.mark.asyncio
  async def test_get_by_id(self, client: AsyncClient, save_fixture: SaveFixture) -> None:
    reading = create_reading()
    await save_fixture(reading)
    reading_id = reading.id

    resp = await client.get(f"/v1/readings/{reading_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(reading_id)

  @pytest.mark.asyncio
  async def test_missing_returns_404(self, client: AsyncClient) -> None:
    resp = await client.get(f"/v1/readings/{uuid4()}")
    assert resp.status_code == 404
