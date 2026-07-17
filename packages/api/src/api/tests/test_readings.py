import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from api.readings import bms
from api.readings.bms import BmsUnreachableError, CaptureResult
from api.readings.decode import decode_blocks
from api.tests.fixtures.database import SaveFixture
from api.tests.fixtures.random_objects import create_reading
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


class TestCaptureReading:
  @pytest.mark.asyncio
  async def test_capture_persists_and_returns_reading(self, client: AsyncClient, mocker: MockerFixture, sample_capture: CaptureResult) -> None:
    mocker.patch("api.readings.bms.capture_reading", return_value=sample_capture)

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
    mocker.patch("api.readings.bms.capture_reading", side_effect=BmsUnreachableError("no Daly BMS found during Bluetooth scan"))

    resp = await client.post("/v1/readings")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "ServiceUnavailableError"
    assert "no Daly BMS found" in body["detail"]

    listed = (await client.get("/v1/readings")).json()
    assert listed["pagination"]["total_count"] == 0

  @pytest.mark.asyncio
  async def test_capture_in_progress_returns_409(self, client: AsyncClient, mocker: MockerFixture) -> None:
    capture = mocker.patch("api.readings.bms.capture_reading")

    await bms.capture_lock.acquire()
    try:
      resp = await client.post("/v1/readings")
    finally:
      bms.capture_lock.release()

    assert resp.status_code == 409
    assert resp.json()["error"] == "ConflictError"
    capture.assert_not_called()


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
