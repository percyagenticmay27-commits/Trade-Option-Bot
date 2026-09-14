import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from option_bot.ai_cio_contract import AiCioContractBuilder


ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).parents[1]


def build(**overrides):
    facts = dict(
        as_of=datetime(2026, 9, 14, 10, 0, tzinfo=ET), session_phase="ENTRY_WINDOW",
        eligible_count=1, open_position_count=0, realized_pnl=Decimal("0"), open_pnl=None,
        risk_used=Decimal("80"), risk_limit=Decimal("200"), best_opportunity="AAPL iron condor",
        freshness="FRESH", health="READY", blockers=(), dashboard_url="/options/OPTION-001",
    )
    facts.update(overrides)
    return AiCioContractBuilder().build(**facts)


def test_exact_identity_paper_status_timestamps_and_risk_math() -> None:
    result = build()
    assert result.module_id == "OPTION-001" and result.strategy_type == "0DTE_OPTIONS"
    assert result.contract_version == "1.0" and result.paper_only is True
    assert result.timestamp_et.endswith("-04:00") and result.timestamp_utc.endswith("+00:00")
    assert result.risk_remaining == "120"


def test_contract_validates_against_json_schema() -> None:
    schema = json.loads((ROOT / "schemas/option-module-summary-v1.schema.json").read_text())
    instance = build().to_dict()
    assert schema["additionalProperties"] is False
    assert set(instance) == set(schema["required"]) == set(schema["properties"])
    for key, rule in schema["properties"].items():
        value = instance[key]
        if "const" in rule:
            assert value == rule["const"]
        allowed = rule.get("type")
        allowed = [allowed] if isinstance(allowed, str) else allowed or []
        type_ok = (
            ("null" in allowed and value is None)
            or ("string" in allowed and isinstance(value, str))
            or ("integer" in allowed and isinstance(value, int) and not isinstance(value, bool))
            or ("array" in allowed and isinstance(value, list))
        )
        if allowed:
            assert type_ok, key


def test_unavailable_fields_are_nullable_with_blockers() -> None:
    result = build(open_pnl=None, best_opportunity=None, freshness="UNAVAILABLE", health="BLOCKED", blockers=("OPTION_DATA_UNAVAILABLE",))
    assert result.open_pnl is None and result.best_opportunity is None
    assert result.blockers == ("OPTION_DATA_UNAVAILABLE",)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://example.test/a", "//evil.test/a"])
def test_rejects_unsafe_dashboard_urls(url) -> None:
    with pytest.raises(ValueError, match="dashboard URL"):
        build(dashboard_url=url)


def test_accepts_https_absolute_dashboard_url() -> None:
    assert build(dashboard_url="https://ai.example.test/options/OPTION-001").dashboard_url.startswith("https://")


def test_serialization_is_deterministic_and_contains_no_sensitive_fields() -> None:
    first = build().canonical_json()
    second = build().canonical_json()
    assert first == second
    lowered = first.lower()
    assert all(term not in lowered for term in ("secret", "api_key", "account_id", "credential"))


def test_blocked_or_unavailable_contract_requires_a_blocker() -> None:
    with pytest.raises(ValueError, match="blocker"):
        build(health="BLOCKED", blockers=())
