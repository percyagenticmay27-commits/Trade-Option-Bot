"""Versioned, source-attributed contract metadata absent from Alpaca payloads."""

from __future__ import annotations

from typing import Final


OIC_SOURCE: Final = "https://www.optionseducation.org/advancedconcepts/equity-vs-index-options"
CBOE_XSP_SOURCE: Final = "https://www.cboe.com/tradable_products/sp_500/mini_spx_options/"
CBOE_DJX_SOURCE: Final = "https://www.cboe.com/tradable_products/dow_jones/djx_options/"

EQUITIES: Final = ("NVDA", "GOOGL", "AAPL", "MSFT", "AMZN", "META", "AVGO", "TSLA")

PRODUCTS: Final = {
    **{
        symbol: {
            "product_type": "EQUITY_OPTION",
            "exercise_style": "AMERICAN",
            "settlement_type": "PHYSICAL",
            "metadata_source": "OIC_EQUITY_VS_INDEX_OPTIONS",
            "source_url": OIC_SOURCE,
        }
        for symbol in EQUITIES
    },
    "XSP": {
        "product_type": "INDEX_OPTION",
        "exercise_style": "EUROPEAN",
        "settlement_type": "CASH",
        "metadata_source": "CBOE_XSP_SPECIFICATION",
        "source_url": CBOE_XSP_SOURCE,
    },
    "DJX": {
        "product_type": "INDEX_OPTION",
        "exercise_style": "EUROPEAN",
        "settlement_type": "CASH",
        "metadata_source": "CBOE_DJX_SPECIFICATION",
        "source_url": CBOE_DJX_SOURCE,
    },
}


def product_metadata(symbol: str) -> dict[str, str] | None:
    value = PRODUCTS.get(symbol)
    return dict(value) if value else None
