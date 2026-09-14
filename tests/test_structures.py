from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from option_bot.evidence import EvidenceBundle
from option_bot.providers.base import Availability, NormalizedOptionContract, OptionSurface
from option_bot.domain import ExerciseStyle, ProductMetadata, SettlementType, StructureType
from option_bot.structures import StructureConfig, StructureGenerator


ET = ZoneInfo("America/New_York")
PRODUCT = ProductMetadata("AAPL", 100, ExerciseStyle.AMERICAN, SettlementType.PHYSICAL, "16:00")


def contract(right, strike, delta, bid="0.30", ask="0.32", gamma="0.03", size=20):
    symbol = f"AAPL-{right}-{strike}"
    return NormalizedOptionContract(symbol, "2026-09-14", right, str(strike), bid, ask, size, size, str(delta), gamma, "-0.2", "0.03", "0.35", 100, 200, datetime(2026, 9, 14, 10, 0, tzinfo=ET), datetime(2026, 9, 14, 10, 0, tzinfo=ET), PRODUCT)


def surface():
    puts = [contract("PUT", 320+i, -d) for i, d in enumerate((.08, .10, .12, .15, .18, .20, .25))]
    calls = [contract("CALL", 340+i, d) for i, d in enumerate((.08, .10, .12, .15, .18, .20, .25))]
    wings = [contract("PUT", 319, -.04, "0.05", "0.06"), contract("CALL", 347, .04, "0.05", "0.06")]
    return OptionSurface("AAPL", "2026-09-14", tuple(puts+calls+wings), "indicative", Availability.AVAILABLE)


def evidence(direction=90, range_score=20):
    return EvidenceBundle(True, direction, range_score, 80, Decimal("1"), "v1", "hash", (), None, None)


def test_enumerates_governed_delta_ladder_and_preserves_rejections() -> None:
    result = StructureGenerator.generate(surface(), evidence(), StructureConfig("BULLISH", Decimal("330"), Decimal("350"), Decimal("331"), Decimal("351"), Decimal("100")))
    attempted = {item.target_delta for item in result.attempts}
    assert attempted == {Decimal("0.08"), Decimal("0.10"), Decimal("0.12"), Decimal("0.15"), Decimal("0.18"), Decimal("0.20")}
    assert any(item.candidate and item.candidate.structure_type is StructureType.PUT_CREDIT_SPREAD for item in result.attempts)
    assert all(item.accepted or item.reason_codes for item in result.attempts)


def test_strong_direction_conditionally_searches_025_and_rejects_risky_width() -> None:
    result = StructureGenerator.generate(surface(), evidence(95), StructureConfig("BULLISH", Decimal("318"), Decimal("350"), Decimal("317"), Decimal("351"), Decimal("40"), allow_delta_25=True))
    assert Decimal("0.25") in {item.target_delta for item in result.attempts}
    assert any("MAX_LOSS_LIMIT" in item.reason_codes for item in result.attempts)


def test_range_regime_generates_asymmetric_condor_and_butterfly_uses_landing_zone() -> None:
    config = StructureConfig("NEUTRAL", Decimal("318"), Decimal("350"), Decimal("317"), Decimal("351"), Decimal("600"), landing_zone=Decimal("340"))
    result = StructureGenerator.generate(surface(), evidence(20, 90), config)
    assert any(item.candidate and item.candidate.structure_type is StructureType.IRON_CONDOR for item in result.attempts)
    assert result.butterfly_body == Decimal("340")


def test_gamma_liquidity_and_boundary_clearance_fail_closed() -> None:
    bad = list(surface().contracts)
    bad[1] = contract("PUT", 321, -.10, bid="0.00", ask="1.00", gamma="0.50", size=0)
    result = StructureGenerator.generate(OptionSurface("AAPL", "2026-09-14", tuple(bad), "indicative", Availability.AVAILABLE), evidence(), StructureConfig("BULLISH", Decimal("320"), Decimal("350"), Decimal("319"), Decimal("351"), Decimal("100")))
    attempt = next(item for item in result.attempts if item.target_delta == Decimal("0.10"))
    assert {"LIQUIDITY_REJECTED", "GAMMA_REJECTED", "TECHNICAL_CLEARANCE_REJECTED"}.issubset(attempt.reason_codes)
