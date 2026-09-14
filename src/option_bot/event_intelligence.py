"""Read-only, source-attributed headline intelligence with fail-closed gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import urlencode
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from option_bot.scheduled_events import OfficialCalendarSource, evaluate_scheduled_calendars


ET = ZoneInfo("America/New_York")
MAX_HEADLINE_AGE_MINUTES = 72 * 60
FUTURE_TIMESTAMP_TOLERANCE_MINUTES = 5
RISK_TERMS = {
    "EARNINGS": ("earnings", "guidance", "quarterly results"),
    "MERGER_ACQUISITION": ("merger", "acquisition", "takeover", "acquire"),
    "REGULATORY_LEGAL": ("sec investigation", "lawsuit", "antitrust", "regulator", "recall"),
    "ANALYST_EVENT": ("analyst day", "investor day", "downgrade", "upgrade"),
    "PRODUCT_EVENT": ("product launch", "unveils", "keynote"),
    "MACRO_FED": ("federal reserve", "fomc", "cpi", "jobs report", "inflation report"),
}


class NewsSource(Protocol):
    name: str

    def fetch(self, symbol: str, retrieved_at: datetime) -> Sequence[Mapping[str, Any]]: ...


def _category(title: str) -> str:
    lowered = title.casefold()
    for category, terms in RISK_TERMS.items():
        if any(term in lowered for term in terms):
            return category
    return "GENERAL_NEWS"


def _iso_et(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("headline timestamp must be timezone-aware")
    return value.astimezone(ET).isoformat()


@dataclass(frozen=True)
class AlphaVantageNewsSource:
    api_key: str
    fetch_json: Callable[[str], Mapping[str, Any]]
    name: str = "ALPHA_VANTAGE"

    def fetch(self, symbol: str, retrieved_at: datetime) -> Sequence[Mapping[str, Any]]:
        query = urlencode(
            {"function": "NEWS_SENTIMENT", "tickers": symbol, "limit": 50, "apikey": self.api_key}
        )
        payload = self.fetch_json(f"https://www.alphavantage.co/query?{query}")
        feed = payload.get("feed")
        if not isinstance(feed, list):
            raise ValueError("Alpha Vantage news feed is unavailable")
        items: list[Mapping[str, Any]] = []
        for raw in feed:
            if not isinstance(raw, Mapping):
                continue
            published = raw.get("time_published")
            title, url = raw.get("title"), raw.get("url")
            if not all(isinstance(value, str) and value for value in (published, title, url)):
                continue
            when = datetime.strptime(published, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            items.append(_normalized(self.name, symbol, title, url, when, retrieved_at))
        return items


@dataclass(frozen=True)
class RssNewsSource:
    name: str
    url_for_symbol: Callable[[str], str]
    fetch_bytes: Callable[[str], bytes]

    def fetch(self, symbol: str, retrieved_at: datetime) -> Sequence[Mapping[str, Any]]:
        root = ElementTree.fromstring(self.fetch_bytes(self.url_for_symbol(symbol)))
        raw_items = root.findall(".//item")
        items: list[Mapping[str, Any]] = []
        invalid_timestamp = False
        for raw in raw_items:
            title = (raw.findtext("title") or "").strip()
            url = (raw.findtext("link") or "").strip()
            published = (raw.findtext("pubDate") or "").strip()
            if not title or not url or not published:
                invalid_timestamp = invalid_timestamp or bool(title and url)
                continue
            try:
                when = parsedate_to_datetime(published)
                items.append(_normalized(self.name, symbol, title, url, when, retrieved_at))
            except (TypeError, ValueError):
                invalid_timestamp = True
        if invalid_timestamp and not items:
            raise ValueError(f"{self.name} returned headlines without usable timestamps")
        return items


def _normalized(
    source: str,
    symbol: str,
    title: str,
    url: str,
    published: datetime,
    retrieved_at: datetime,
) -> Mapping[str, Any]:
    if published.tzinfo is None or retrieved_at.tzinfo is None:
        raise ValueError("headline and retrieval timestamps must be timezone-aware")
    age_minutes = int((retrieved_at.astimezone(timezone.utc) - published.astimezone(timezone.utc)).total_seconds() // 60)
    freshness = (
        "FRESH"
        if -FUTURE_TIMESTAMP_TOLERANCE_MINUTES <= age_minutes <= MAX_HEADLINE_AGE_MINUTES
        else ("FUTURE" if age_minutes < -FUTURE_TIMESTAMP_TOLERANCE_MINUTES else "STALE")
    )
    return {
        "title": title.strip(),
        "url": url.strip(),
        "published_at_et": _iso_et(published),
        "retrieved_at_et": _iso_et(retrieved_at),
        "symbol": symbol,
        "category": _category(title),
        "age_minutes": age_minutes,
        "freshness": freshness,
        "sources": [source],
    }


def _deduplicate(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (str(item["url"]).rstrip("/"), str(item["title"]).strip().casefold())
        if key not in merged:
            merged[key] = dict(item)
        else:
            merged[key]["sources"] = sorted(
                set(merged[key]["sources"]) | set(item["sources"])
            )
    return sorted(merged.values(), key=lambda item: (item["published_at_et"], item["title"]), reverse=True)


def build_event_intelligence_report(
    *,
    symbols: Sequence[str],
    sources: Sequence[NewsSource],
    retrieved_at: datetime,
    scheduled_sources: Sequence[OfficialCalendarSource] = (),
) -> Mapping[str, Any]:
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at must be timezone-aware")
    symbol_reports: list[Mapping[str, Any]] = []
    for symbol in symbols:
        collected: list[Mapping[str, Any]] = []
        statuses: dict[str, str] = {}
        for source in sources:
            try:
                collected.extend(source.fetch(symbol, retrieved_at))
                statuses[source.name] = "AVAILABLE"
            except (ConnectionError, OSError, TimeoutError, ValueError, ElementTree.ParseError):
                statuses[source.name] = "UNAVAILABLE"
        headlines = _deduplicate(collected)
        available = any(status == "AVAILABLE" for status in statuses.values())
        actionable = [item for item in headlines if item["freshness"] == "FRESH"]
        risk = any(item["category"] != "GENERAL_NEWS" for item in actionable)
        headline_gate = "BLOCKED" if risk else ("CLEAR" if available else "UNAVAILABLE")
        reasons = []
        if risk:
            reasons.append("RISK_HEADLINE_REQUIRES_REVIEW")
        if not available:
            reasons.append("HEADLINE_SOURCES_UNAVAILABLE")
        elif any(status == "UNAVAILABLE" for status in statuses.values()):
            reasons.append("PARTIAL_HEADLINE_SOURCES_UNAVAILABLE")
        symbol_reports.append(
            {
                "symbol": symbol,
                "headline_gate": headline_gate,
                "source_status": statuses,
                "headlines": headlines,
                "headline_count": len(headlines),
                "actionable_headline_count": len(actionable),
                "reason_codes": reasons,
            }
        )
    scheduled = evaluate_scheduled_calendars(scheduled_sources, retrieved_at.astimezone(ET).date())
    return {
        "module_id": "OPTION-001",
        "paper_only": True,
        "order_submission_enabled": False,
        "retrieved_at_et": _iso_et(retrieved_at),
        "event_gate": scheduled["gate"],
        "scheduled_calendar_status": scheduled["status"],
        "scheduled_source_status": scheduled["source_status"],
        "scheduled_events": scheduled["events"],
        "reason_codes": scheduled["reason_codes"],
        "symbols": symbol_reports,
    }
