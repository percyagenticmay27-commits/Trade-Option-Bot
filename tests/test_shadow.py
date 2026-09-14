from datetime import datetime, timezone
from decimal import Decimal

import pytest

from option_bot.shadow import ShadowLearner, ShadowPrediction
from option_bot.storage import AuditRepository


def test_shadow_predictions_are_stored_but_cannot_change_active_score(tmp_path) -> None:
    repo = AuditRepository(tmp_path / "audit.sqlite3")
    learner = ShadowLearner(repo)
    first = learner.observe(ShadowPrediction("AAPL", Decimal("0.90"), "up", "shadow-v1"), "cycle-1", Decimal("8.0"), datetime.now(timezone.utc))
    second = learner.observe(ShadowPrediction("AAPL", Decimal("0.10"), "down", "shadow-v1"), "cycle-2", Decimal("8.0"), datetime.now(timezone.utc))
    assert first.active_rank_score == second.active_rank_score == Decimal("8.0")
    assert repo.count("evidence") == 2 and not learner.promotion_enabled


def test_runtime_cannot_enable_shadow_promotion(tmp_path) -> None:
    with pytest.raises(ValueError, match="offline validation"):
        ShadowLearner(AuditRepository(tmp_path / "audit.sqlite3"), promote=True)
