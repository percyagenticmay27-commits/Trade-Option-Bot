from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from option_bot.event_intelligence import (
    AlphaVantageNewsSource,
    RssNewsSource,
    build_event_intelligence_report,
)
from option_bot.scheduled_events import OfficialCalendarSource


ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 14, 10, 0, tzinfo=ET)


def test_normalizes_deduplicates_and_blocks_on_risk_headline() -> None:
    alpha = AlphaVantageNewsSource(
        "secret-value",
        lambda _url: {
            "feed": [
                {
                    "title": "Apple schedules earnings update",
                    "url": "https://example.test/apple",
                    "time_published": "20260914T130000",
                    "ticker_sentiment": [{"ticker": "AAPL", "relevance_score": "0.91"}],
                }
            ]
        },
    )
    rss = RssNewsSource(
        "GOOGLE_NEWS",
        lambda _symbol: "https://news.test/rss",
        lambda _url: b"""<rss><channel><item>
          <title>Apple schedules earnings update</title>
          <link>https://example.test/apple</link>
          <pubDate>Mon, 14 Sep 2026 13:00:00 GMT</pubDate>
        </item></channel></rss>""",
    )

    report = build_event_intelligence_report(
        symbols=("AAPL",), sources=(alpha, rss), retrieved_at=NOW
    )

    item = report["symbols"][0]["headlines"][0]
    assert len(report["symbols"][0]["headlines"]) == 1
    assert item["category"] == "EARNINGS"
    assert item["published_at_et"] == "2026-09-14T09:00:00-04:00"
    assert item["sources"] == ["ALPHA_VANTAGE", "GOOGLE_NEWS"]
    assert report["symbols"][0]["headline_gate"] == "BLOCKED"
    assert "secret-value" not in str(report)


def test_news_cannot_clear_missing_scheduled_calendar_gate() -> None:
    empty = RssNewsSource(
        "YAHOO_FINANCE",
        lambda _symbol: "https://finance.test/rss",
        lambda _url: b"<rss><channel/></rss>",
    )
    report = build_event_intelligence_report(
        symbols=("AAPL",), sources=(empty,), retrieved_at=NOW
    )

    assert report["event_gate"] == "BLOCKED"
    assert report["scheduled_calendar_status"] == "UNAVAILABLE"
    assert "SCHEDULED_EVENT_GATE_UNAVAILABLE" in report["reason_codes"]
    assert report["symbols"][0]["headline_gate"] == "CLEAR"


def test_source_failure_is_reported_and_fails_headline_gate_closed() -> None:
    broken = RssNewsSource(
        "GOOGLE_NEWS",
        lambda _symbol: "https://news.test/rss",
        lambda _url: (_ for _ in ()).throw(TimeoutError()),
    )
    report = build_event_intelligence_report(
        symbols=("AAPL",), sources=(broken,), retrieved_at=NOW
    )

    symbol = report["symbols"][0]
    assert symbol["headline_gate"] == "UNAVAILABLE"
    assert symbol["source_status"] == {"GOOGLE_NEWS": "UNAVAILABLE"}
    assert "HEADLINE_SOURCES_UNAVAILABLE" in symbol["reason_codes"]


def test_rss_rejects_missing_timestamp_instead_of_inventing_one() -> None:
    source = RssNewsSource(
        "YAHOO_FINANCE",
        lambda _symbol: "https://finance.test/rss",
        lambda _url: b"""<rss><channel><item>
          <title>AAPL product news</title><link>https://example.test/item</link>
        </item></channel></rss>""",
    )
    report = build_event_intelligence_report(
        symbols=("AAPL",), sources=(source,), retrieved_at=NOW
    )

    assert report["symbols"][0]["headline_gate"] == "UNAVAILABLE"
    assert report["symbols"][0]["headlines"] == []


def test_stale_risk_headline_is_retained_but_cannot_block_today() -> None:
    old = (NOW - timedelta(days=5)).astimezone(ZoneInfo("UTC"))
    source = RssNewsSource(
        "GOOGLE_NEWS",
        lambda _symbol: "https://news.test/rss",
        lambda _url: (
            "<rss><channel><item>"
            "<title>AAPL earnings warning</title>"
            "<link>https://example.test/old</link>"
            f"<pubDate>{old.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>"
            "</item></channel></rss>"
        ).encode(),
    )
    report = build_event_intelligence_report(
        symbols=("AAPL",), sources=(source,), retrieved_at=NOW
    )

    symbol = report["symbols"][0]
    assert symbol["headline_gate"] == "CLEAR"
    assert symbol["headline_count"] == 1
    assert symbol["actionable_headline_count"] == 0
    assert symbol["headlines"][0]["freshness"] == "STALE"


def test_all_official_calendars_must_clear_before_event_gate_clears() -> None:
    calendar = OfficialCalendarSource(
        "OFFICIAL_TEST", "https://official.test/calendar", lambda _: b"ok", lambda *_: []
    )
    report = build_event_intelligence_report(
        symbols=("AAPL",), sources=(), retrieved_at=NOW, scheduled_sources=(calendar,)
    )
    assert report["scheduled_calendar_status"] == "AVAILABLE"
    assert report["event_gate"] == "CLEAR"
    assert report["scheduled_source_status"] == {"OFFICIAL_TEST": "AVAILABLE"}
