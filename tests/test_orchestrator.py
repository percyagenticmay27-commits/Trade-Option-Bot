from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from option_bot.config import REQUIRED_SYMBOLS
from option_bot.domain import Decision, StructureType
from option_bot.orchestrator import DailyOrchestrator, SymbolEvaluation
from option_bot.portfolio import PortfolioSelector, SelectableCandidate
from option_bot.storage import AuditRepository


ET = ZoneInfo("America/New_York")


def at(hour, minute=0):
    return datetime(2026, 9, 14, hour, minute, tzinfo=ET)


def evaluation(symbol):
    candidate = None
    if symbol == "AAPL":
        candidate = SelectableCandidate("AAPL", "aapl-condor", StructureType.IRON_CONDOR, Decimal("9"), Decimal("80"), "technology")
    return SymbolEvaluation(symbol, Decision.TRADE if candidate else Decision.NO_TRADE, candidate, ())


def make(tmp_path, market_open=True, outage=False, submitter=None):
    repo = AuditRepository(tmp_path / "audit.sqlite3")
    evaluator = (lambda _: (_ for _ in ()).throw(ConnectionError())) if outage else evaluation
    return DailyOrchestrator(REQUIRED_SYMBOLS, evaluator, PortfolioSelector(), repo, lambda _: market_open, submitter)


def test_complete_12_symbol_leaderboard_and_one_selection(tmp_path) -> None:
    result = make(tmp_path).run_cycle(at(10), "cycle-1")
    assert len(result.leaderboard) == 12
    assert tuple(row.symbol for row in result.leaderboard) == REQUIRED_SYMBOLS
    assert [x.symbol for x in result.selected] == ["AAPL"]


def test_duplicate_cycle_is_idempotent_across_second_process(tmp_path) -> None:
    submissions = []
    first = make(tmp_path, submitter=lambda item: submissions.append(item.candidate_id)).run_cycle(at(10), "cycle-1")
    second = make(tmp_path, submitter=lambda item: submissions.append(item.candidate_id)).run_cycle(at(10), "cycle-1")
    assert first.canonical_json() == second.canonical_json()
    assert submissions == ["aapl-condor"]


def test_market_closed_before_and_after_window_do_not_enter(tmp_path) -> None:
    assert make(tmp_path, market_open=False).run_cycle(at(10), "closed").reason_codes == ("MARKET_CLOSED",)
    assert make(tmp_path).run_cycle(at(9, 44), "early").reason_codes == ("BEFORE_ENTRY_WINDOW",)
    assert make(tmp_path).run_cycle(at(10, 31), "late").reason_codes == ("AFTER_ENTRY_WINDOW",)


def test_provider_outage_returns_complete_unavailable_leaderboard(tmp_path) -> None:
    result = make(tmp_path, outage=True).run_cycle(at(10), "outage")
    assert len(result.leaderboard) == 12 and result.selected == ()
    assert all(row.decision is Decision.DATA_UNAVAILABLE for row in result.leaderboard)


def test_1530_cycle_requests_position_management_not_entry(tmp_path) -> None:
    result = make(tmp_path).run_cycle(at(15, 30), "close")
    assert result.manage_positions and result.reason_codes == ("MANDATORY_EXIT_WINDOW",)
