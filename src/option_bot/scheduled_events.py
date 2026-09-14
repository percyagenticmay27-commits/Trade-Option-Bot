"""Official Fed/BLS/BEA scheduled-event evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from html.parser import HTMLParser
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BEA_URL = "https://www.bea.gov/news/schedule"
MONTHS = {
    name: number
    for number, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
        1,
    )
}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if clean:
            self.parts.append(clean)


def _text(payload: bytes) -> str:
    parser = _Text()
    parser.feed(payload.decode("utf-8", errors="strict"))
    return "\n".join(parser.parts)


def parse_bls_ics(payload: bytes, trade_date: date) -> list[Mapping[str, Any]]:
    text = payload.decode("utf-8", errors="strict").replace("\r\n ", "")
    if "BEGIN:VCALENDAR" not in text:
        raise ValueError("BLS calendar signature missing")
    events: list[Mapping[str, Any]] = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, flags=re.S):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.split(";", 1)[0]] = value.strip()
        raw_time = fields.get("DTSTART", "")
        try:
            if raw_time.endswith("Z"):
                scheduled = datetime.strptime(raw_time, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(ET)
            else:
                scheduled = datetime.strptime(raw_time, "%Y%m%dT%H%M%S").replace(tzinfo=ET)
        except ValueError:
            continue
        if scheduled.date() == trade_date:
            events.append({
                "source": "BLS",
                "kind": "ECONOMIC_RELEASE",
                "title": fields.get("SUMMARY", "BLS economic release"),
                "scheduled_at_et": scheduled.isoformat(),
                "url": fields.get("URL", BLS_URL),
            })
    return events


def parse_fomc_calendar(payload: bytes, trade_date: date) -> list[Mapping[str, Any]]:
    text = _text(payload)
    marker = f"{trade_date.year} FOMC Meetings"
    if marker not in text:
        raise ValueError("Federal Reserve calendar year missing")
    section = text.split(marker, 1)[1]
    section = re.split(r"\d{4} FOMC Meetings", section, maxsplit=1)[0]
    matches = re.findall(
        r"\b(" + "|".join(MONTHS) + r")\b\s+([0-9]{1,2})(?:-([0-9]{1,2}))?\*?",
        section,
    )
    if not matches:
        raise ValueError("Federal Reserve meeting entries missing")
    events: list[Mapping[str, Any]] = []
    for month_name, first, last in matches:
        start, end = int(first), int(last or first)
        if MONTHS[month_name] == trade_date.month and start <= trade_date.day <= end:
            events.append({
                "source": "FEDERAL_RESERVE",
                "kind": "FOMC_MEETING_DAY",
                "title": f"FOMC meeting — {month_name} {start}-{end}, {trade_date.year}",
                "scheduled_at_et": None,
                "url": FED_URL,
            })
    return events


def parse_bea_schedule(payload: bytes, trade_date: date) -> list[Mapping[str, Any]]:
    text = _text(payload)
    if "Release Schedule" not in text or f"Year {trade_date.year}" not in text:
        raise ValueError("BEA release schedule signature missing")
    month = next(name for name, number in MONTHS.items() if number == trade_date.month)
    pattern = re.compile(
        rf"{month}\s+{trade_date.day}\s+([0-9]{{1,2}}:[0-9]{{2}}\s+(?:AM|PM))\s+(.+?)(?=\n(?:{'|'.join(MONTHS)})\s+[0-9]|\Z)",
        flags=re.S,
    )
    events: list[Mapping[str, Any]] = []
    for clock, title_block in pattern.findall(text):
        scheduled_time = datetime.strptime(clock, "%I:%M %p").time()
        scheduled = datetime.combine(trade_date, scheduled_time, tzinfo=ET)
        title = " ".join(title_block.splitlines()).strip()
        events.append({
            "source": "BEA",
            "kind": "ECONOMIC_RELEASE",
            "title": title,
            "scheduled_at_et": scheduled.isoformat(),
            "url": BEA_URL,
        })
    return events


@dataclass(frozen=True)
class OfficialCalendarSource:
    name: str
    url: str
    fetch_bytes: Callable[[str], bytes]
    parser: Callable[[bytes, date], Sequence[Mapping[str, Any]]]

    def fetch(self, trade_date: date) -> Sequence[Mapping[str, Any]]:
        return self.parser(self.fetch_bytes(self.url), trade_date)


def evaluate_scheduled_calendars(
    sources: Sequence[OfficialCalendarSource], trade_date: date
) -> Mapping[str, Any]:
    statuses: dict[str, str] = {}
    events: list[Mapping[str, Any]] = []
    for source in sources:
        try:
            events.extend(source.fetch(trade_date))
            statuses[source.name] = "AVAILABLE"
        except (ConnectionError, OSError, TimeoutError, UnicodeError, ValueError):
            statuses[source.name] = "UNAVAILABLE"
    unavailable = not sources or any(value != "AVAILABLE" for value in statuses.values())
    return {
        "status": "UNAVAILABLE" if unavailable else "AVAILABLE",
        "gate": "BLOCKED" if unavailable or events else "CLEAR",
        "source_status": statuses,
        "events": sorted(events, key=lambda item: (str(item.get("scheduled_at_et")), str(item.get("title")))),
        "reason_codes": (
            ["SCHEDULED_EVENT_GATE_UNAVAILABLE"] if unavailable
            else (["SCHEDULED_EVENT_TODAY"] if events else [])
        ),
    }
