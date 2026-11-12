"""Observation-only early-reversal signal (not an alternative paper execution).

Uses only already-computed completed-price-bar indicators; omits the EMA50
slope veto strictly for comparison. No option legs, fills, win/loss, or orders.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal

def evaluate(symbol, indicators, now:datetime):
    result={'strategy':'EARLY_REVERSAL_EMA9_20_SHADOW','symbol':symbol,
            'at':now.isoformat(),'status':'DATA_UNAVAILABLE','reason':'COMPLETED_BARS_UNAVAILABLE',
            'paper_only':True,'paper_entries':0,'broker_submissions':0,
            'options_evaluation':'NOT_PERFORMED','pnl_status':'NOT_MEASURABLE_NO_VERIFIED_FILLS'}
    if not indicators.available:return result
    p=indicators.price;v=indicators.vwap
    ema9=indicators.ema9;ema20=indicators.ema20
    ema50=indicators.ema50;slope=indicators.ema50_slope
    rel=indicators.relative_volume
    if any(x is None for x in (p,v,ema9,ema20,ema50,slope,rel)):
        result['reason']='REQUIRED_INDICATORS_UNAVAILABLE';return result
    # This is a price-action observation, NOT a replacement of EMA50 entry
    # governance, not a claim that this will be profitable.
    bull=p>v and p>ema9>ema20 and rel>=1
    bear=p<v and p<ema9<ema20 and rel>=1
    trend_bull=p>v and p>ema50 and slope>0
    trend_bear=p<v and p<ema50 and slope<0
    result.update(status='SIGNAL_OBSERVED' if bull or bear else 'NO_SIGNAL',
                  direction='BULLISH' if bull else 'BEARISH' if bear else None,
                  reason='EARLY_REVERSAL_OBSERVED' if bull or bear else 'EMA9_EMA20_VOLUME_NOT_ALIGNED',
                  strict_ema50_would_allow=(trend_bull if bull else trend_bear if bear else None),
                  evidence={'price':str(p),'vwap':str(v),'ema9':str(ema9),
                            'ema20':str(ema20),'ema50':str(ema50),'ema50_slope':str(slope),
                            'relative_volume':str(rel)})
    return result
