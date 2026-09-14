from datetime import date

from option_bot.scheduled_events import (
    OfficialCalendarSource,
    evaluate_scheduled_calendars,
    parse_bea_schedule,
    parse_bls_ics,
    parse_fomc_calendar,
)


def test_bls_ics_parses_same_day_release_with_et_time() -> None:
    payload = b"""BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260914T123000Z
SUMMARY:Employment Situation
URL:https://www.bls.gov/news.release/empsit.nr0.htm
END:VEVENT
END:VCALENDAR"""
    events = parse_bls_ics(payload, date(2026, 9, 14))
    assert events == [{
        "source": "BLS",
        "kind": "ECONOMIC_RELEASE",
        "title": "Employment Situation",
        "scheduled_at_et": "2026-09-14T08:30:00-04:00",
        "url": "https://www.bls.gov/news.release/empsit.nr0.htm",
    }]


def test_fomc_parser_blocks_each_day_of_two_day_meeting() -> None:
    html = b"""<h4>2026 FOMC Meetings</h4><div>September</div><div>15-16*</div>
    <div>October</div><div>27-28</div><h4>2025 FOMC Meetings</h4>"""
    events = parse_fomc_calendar(html, date(2026, 9, 15))
    assert events[0]["source"] == "FEDERAL_RESERVE"
    assert events[0]["kind"] == "FOMC_MEETING_DAY"
    assert events[0]["scheduled_at_et"] is None


def test_bea_parser_parses_official_release_schedule() -> None:
    html = b"""<h1>Release Schedule</h1><div>Year 2026</div>
    <div>September 14</div><div>8:30 AM</div><div>Gross Domestic Product</div>"""
    events = parse_bea_schedule(html, date(2026, 9, 14))
    assert events[0]["source"] == "BEA"
    assert events[0]["scheduled_at_et"] == "2026-09-14T08:30:00-04:00"


def test_calendar_gate_requires_every_official_source_to_be_evaluable() -> None:
    sources = (
        OfficialCalendarSource("FEDERAL_RESERVE", "https://fed.test", lambda _: b"x", lambda *_: []),
        OfficialCalendarSource("BLS", "https://bls.test", lambda _: (_ for _ in ()).throw(TimeoutError()), lambda *_: []),
        OfficialCalendarSource("BEA", "https://bea.test", lambda _: b"x", lambda *_: []),
    )
    result = evaluate_scheduled_calendars(sources, date(2026, 9, 14))
    assert result["status"] == "UNAVAILABLE"
    assert result["gate"] == "BLOCKED"
    assert result["source_status"]["BLS"] == "UNAVAILABLE"


def test_calendar_gate_blocks_when_official_event_exists() -> None:
    event = {"source": "BLS", "kind": "ECONOMIC_RELEASE"}
    sources = (
        OfficialCalendarSource("BLS", "https://bls.test", lambda _: b"x", lambda *_: [event]),
    )
    result = evaluate_scheduled_calendars(sources, date(2026, 9, 14))
    assert result["status"] == "AVAILABLE"
    assert result["gate"] == "BLOCKED"
    assert result["events"] == [event]
