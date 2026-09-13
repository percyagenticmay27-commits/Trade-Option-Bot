from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from option_bot.providers.base import Availability
from option_bot.providers.events import AggregatingEventProvider


ET = ZoneInfo("America/New_York")
START = datetime(2026, 9, 14, 9, 30, tzinfo=ET)


def test_event_gate_blocks_when_every_source_is_unavailable() -> None:
    gate = AggregatingEventProvider([lambda *_: (_ for _ in ()).throw(TimeoutError())]).get_event_gate("AAPL", (START, START + timedelta(hours=7)))
    assert gate.availability is Availability.UNAVAILABLE
    assert gate.blocked and gate.reason_codes == ("EVENT_SOURCES_UNAVAILABLE",)


def test_event_gate_aggregates_binary_events() -> None:
    source = lambda *_: [{"kind": "earnings", "time": "2026-09-14T16:05:00-04:00", "title": "AAPL earnings"}]
    gate = AggregatingEventProvider([source]).get_event_gate("AAPL", (START, START + timedelta(hours=8)))
    assert gate.availability is Availability.AVAILABLE and gate.blocked
    assert gate.events[0]["kind"] == "earnings"


def test_event_gate_is_clear_when_authoritative_source_succeeds_empty() -> None:
    gate = AggregatingEventProvider([lambda *_: []]).get_event_gate("AAPL", (START, START + timedelta(hours=7)))
    assert gate.availability is Availability.AVAILABLE and not gate.blocked
