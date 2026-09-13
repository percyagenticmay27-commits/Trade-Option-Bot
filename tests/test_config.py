from pathlib import Path

import pytest

from option_bot.config import ConfigError, OptionBotConfig
from option_bot.domain import OperatingMode, StrategyType


PAPER_URL = "https://paper-api.alpaca.markets"


def environment(**overrides: str) -> dict[str, str]:
    values = {
        "APCA_API_KEY_ID": "paper-key",
        "APCA_API_SECRET_KEY": "paper-secret",
        "APCA_API_BASE_URL": PAPER_URL,
        "OPTION_BOT_TIMEZONE": "America/New_York",
        "OPTION_BOT_DB_PATH": "results/option_bot.sqlite3",
    }
    values.update(overrides)
    return values


def test_loads_exact_paper_configuration(tmp_path: Path) -> None:
    config_file = tmp_path / "option-001.json"
    config_file.write_text(
        '{"module_id":"OPTION-001","strategy_type":"0DTE_OPTIONS",'
        '"symbols":["NVDA","GOOGL","AAPL","MSFT","AMZN","META","AVGO","TSLA",'
        '"XSP","MRUT","MBTX","DJX"],"max_loss_per_trade":"100.00",'
        '"max_daily_defined_loss":"200.00","max_daily_entries":2,'
        '"entry_start":"09:45","entry_end":"10:30","mandatory_exit":"15:30",'
        '"enabled_strategy_types":["0DTE_OPTIONS"]}',
        encoding="utf-8",
    )

    config = OptionBotConfig.load(environment(), config_file)

    assert config.operating_mode is OperatingMode.PAPER
    assert config.strategy_type is StrategyType.ODTE_OPTIONS
    assert config.paper_only is True
    assert config.symbols == (
        "NVDA", "GOOGL", "AAPL", "MSFT", "AMZN", "META", "AVGO", "TSLA",
        "XSP", "MRUT", "MBTX", "DJX",
    )
    assert str(config.max_loss_per_trade) == "100.00"
    assert str(config.max_daily_defined_loss) == "200.00"
    assert config.max_daily_entries == 2
    assert StrategyType.WHEEL_OPTIONS not in config.enabled_strategy_types


@pytest.mark.parametrize(
    "url",
    [
        "https://api.alpaca.markets",
        "http://paper-api.alpaca.markets",
        "https://paper-api.alpaca.markets.evil.example",
        "not-a-url",
        "",
    ],
)
def test_rejects_every_non_exact_paper_url(tmp_path: Path, url: str) -> None:
    config_file = Path("configs/option-001.json")
    with pytest.raises(ConfigError, match="paper endpoint"):
        OptionBotConfig.load(environment(APCA_API_BASE_URL=url), config_file)


@pytest.mark.parametrize("missing", ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"])
def test_rejects_missing_credentials(missing: str) -> None:
    values = environment()
    values.pop(missing)
    with pytest.raises(ConfigError, match=missing):
        OptionBotConfig.load(values, Path("configs/option-001.json"))


def test_rejects_non_eastern_timezone() -> None:
    with pytest.raises(ConfigError, match="America/New_York"):
        OptionBotConfig.load(
            environment(OPTION_BOT_TIMEZONE="UTC"), Path("configs/option-001.json")
        )
