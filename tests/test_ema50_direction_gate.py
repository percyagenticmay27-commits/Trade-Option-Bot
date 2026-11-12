"""EMA50 must validate directional entries, never invent warmup bars."""
from dataclasses import replace
from decimal import Decimal as D
from option_bot.collection_policy import collection_plan
from test_directional_gate import snapshot


def base(price='110',vwap='100',ema50='105',slope='0.4',adx=25,chop=40):
    return replace(snapshot(),price=D(price),vwap=D(vwap),ema50=D(ema50) if ema50 is not None else None,
                   ema50_slope=D(slope) if slope is not None else None,adx14=adx,chop14=chop)

def test_bullish_requires_vwap_price_above_ema50_and_rising_slope():
    p=collection_plan(base())
    assert p['status']=='AVAILABLE' and p['bias']=='BULLISH'
    assert 'PUT_CREDIT_SPREAD' in p['strategies']

def test_bearish_requires_vwap_price_below_ema50_and_falling_slope():
    p=collection_plan(base('90','100','95','-0.4'))
    assert p['status']=='AVAILABLE' and p['bias']=='BEARISH'
    assert p['strategies']==['CALL_CREDIT_SPREAD']

def test_vwap_above_but_ema50_falling_blocks_direction():
    p=collection_plan(base(slope='-0.4'))
    assert p['status']=='WAIT_FOR_TREND_CONFIRMATION' and p['bias'] is None
    assert p['candidate_option_types']==[]

def test_vwap_below_but_ema50_rising_blocks_direction():
    p=collection_plan(base('90','100','95','0.4'))
    assert p['status']=='WAIT_FOR_TREND_CONFIRMATION' and p['bias'] is None

def test_price_against_ema50_blocks_direction():
    p=collection_plan(base(price='110',ema50='115'))
    assert p['status']=='WAIT_FOR_TREND_CONFIRMATION'

def test_missing_ema50_blocks_and_requests_more_bars():
    p=collection_plan(base(ema50=None,slope=None))
    assert p['status']=='DATA_UNAVAILABLE' and 'EMA50' in p['reason']

def test_flat_ema50_blocks_direction():
    assert collection_plan(base(slope='0'))['status']=='WAIT_FOR_TREND_CONFIRMATION'

def test_neutral_regime_preserves_condor_when_ema50_exists():
    p=collection_plan(base(adx=15,chop=60))
    assert p['bias']=='NEUTRAL' and 'IRON_CONDOR' in p['strategies']

def test_indicator_warms_ema50_only_from_53_completed_bars():
    from datetime import datetime,timedelta
    from option_bot.indicators import Bar,IndicatorEngine,ema
    t=datetime.fromisoformat('2026-11-11T09:30:00-05:00')
    bars=tuple(Bar(t+timedelta(minutes=5*i),D(100+i),D(101+i),D(99+i),D(100+i),1000) for i in range(55))
    result=IndicatorEngine.compute(bars,bars,{'average_volume':1000})
    assert result.ema50==ema([b.close for b in bars],50)[-1]
    assert result.ema50_slope>0
    insufficient=IndicatorEngine.compute(bars[:52],bars[:52],{'average_volume':1000})
    assert insufficient.ema50 is None and insufficient.ema50_slope is None
