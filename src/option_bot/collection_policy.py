"""Directional entry routing must agree with VWAP and the 5m EMA50 trend."""
from dataclasses import asdict


def collection_plan(indicators):
    if not indicators.available:
        return {"status":"DATA_UNAVAILABLE","bias":None,"candidate_option_types":[],
                "strategies":[],"directional_debit_enabled":False,"reason":"DIRECTION_EVIDENCE_UNAVAILABLE"}
    neutral=indicators.adx14<=20 and indicators.chop14>=55
    if neutral:
        bias='NEUTRAL'
    else:
        ema50=indicators.ema50
        slope=indicators.ema50_slope
        if ema50 is None or slope is None:
            reason='EMA50_WARMUP_UNAVAILABLE_REQUIRE_53_COMPLETED_5MIN_BARS'
        elif indicators.price>indicators.vwap and indicators.price>ema50 and slope>0:
            reason=None;bias='BULLISH'
        elif indicators.price<indicators.vwap and indicators.price<ema50 and slope<0:
            reason=None;bias='BEARISH'
        else:
            reason='VWAP_EMA50_TREND_CONFLICT'
        if reason:
            return {"status":"WAIT_FOR_TREND_CONFIRMATION" if reason=="VWAP_EMA50_TREND_CONFLICT" else "DATA_UNAVAILABLE","bias":None,"candidate_option_types":[],
                    "strategies":[],"directional_debit_enabled":False,"reason":reason,
                    "ema50":str(ema50) if ema50 is not None else None,
                    "ema50_slope":str(slope) if slope is not None else None,
                    "policy":"VWAP_PLUS_5MIN_EMA50_DIRECTION_V1"}
    return {"status":"AVAILABLE","bias":bias,
            "candidate_option_types":{"BULLISH":["put","call"],"BEARISH":["call"],"NEUTRAL":["put","call"]}[bias],
            "strategies":{"BULLISH":["PUT_CREDIT_SPREAD","CALL_DEBIT_SPREAD"],"BEARISH":["CALL_CREDIT_SPREAD"],
                          "NEUTRAL":["IRON_CONDOR","IRON_BUTTERFLY"]}[bias],
            "directional_debit_enabled":bias=="BULLISH","indicators":asdict(indicators),
            "held_legs":"ALWAYS_REFRESH_ALL_SIDES",
            "policy":"VWAP_PLUS_5MIN_EMA50_DIRECTION_V1"}
