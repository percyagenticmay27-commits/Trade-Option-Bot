"""Versioned opening-range research policy; never authorizes broker orders."""
from datetime import time, timedelta
from decimal import Decimal as D
from math import isfinite
from zoneinfo import ZoneInfo
from option_bot.indicators import session_vwap

ET = ZoneInfo('America/New_York')
STRATEGY = 'OPENING_RANGE_VWAP_REGIME_SHADOW_V1'


def evaluate(symbol, indicators, bars, now):
    out = dict(strategy=STRATEGY, symbol=symbol, at=now.isoformat(),
               status='DATA_UNAVAILABLE', direction=None, reason='COMPLETED_BARS_UNAVAILABLE',
               paper_only=True, broker_submissions=0, evidence={})
    def stop(reason, status='WAIT'):
        out.update(status=status, reason=reason)
        return out
    if now.tzinfo is None:
        return stop('TIMEZONE_REQUIRED', 'DATA_UNAVAILABLE')
    observed = now.astimezone(ET)
    rows = sorted((b for b in bars if b.timestamp.tzinfo is not None
                   and b.timestamp + timedelta(minutes=5) <= now
                   and time(9,30) <= b.timestamp.astimezone(ET).time().replace(tzinfo=None) < time(16)),
                  key=lambda b:b.timestamp)
    current = [b for b in rows if b.timestamp.astimezone(ET).date() == observed.date()]
    if not current:
        return stop('CURRENT_SESSION_BARS_UNAVAILABLE', 'DATA_UNAVAILABLE')
    if any(b.volume <= 0 or not (0 < b.low <= min(b.open,b.close) <= max(b.open,b.close) <= b.high)
           for b in rows):
        return stop('INVALID_OHLC_OR_VOLUME', 'DATA_UNAVAILABLE')
    if now - (current[-1].timestamp + timedelta(minutes=5)) > timedelta(minutes=5):
        return stop('COMPLETED_BARS_STALE', 'DATA_UNAVAILABLE')
    if any(y.timestamp-x.timestamp != timedelta(minutes=5) for x,y in zip(current,current[1:])):
        return stop('CURRENT_SESSION_GRID_INCOMPLETE', 'DATA_UNAVAILABLE')
    if len(current)<3:
        return stop('OPENING_RANGE_NOT_COMPLETE')
    if [b.timestamp.astimezone(ET).time().replace(tzinfo=None) for b in current[:3]] != [time(9,30),time(9,35),time(9,40)]:
        return stop('OPENING_RANGE_GRID_INCOMPLETE', 'DATA_UNAVAILABLE')
    low=min(b.low for b in current[:3]); high=max(b.high for b in current[:3])
    out['evidence'].update(opening_range_low=str(low),opening_range_high=str(high),
        opening_range_fixed_at_ct='08:45',current_completed_bars=len(current),
        last_completed_bar=current[-1].timestamp.isoformat())
    if len(current)<5:
        return stop('WAIT_FOR_TWO_POST_OPENING_RANGE_BARS')
    if not indicators.available or not all(isfinite(float(x)) for x in (indicators.atr14,indicators.adx14,indicators.chop14)) or indicators.atr14<=0:
        return stop('INDICATOR_WARMUP_UNAVAILABLE', 'DATA_UNAVAILABLE')
    # Compare the same three completed five-minute slots across prior sessions.
    # Missing slots never enter the denominator; no comparison with midday volume.
    slots=[b.timestamp.astimezone(ET).time().replace(tzinfo=None) for b in current[-3:]]
    dates=sorted({b.timestamp.astimezone(ET).date() for b in rows
                  if b.timestamp.astimezone(ET).date()<observed.date()})[-20:]
    volumes=[]
    for day in dates:
        matching=[b for b in rows if b.timestamp.astimezone(ET).date()==day
                  and b.timestamp.astimezone(ET).time().replace(tzinfo=None) in slots]
        if len(matching)==3 and len({b.timestamp for b in matching})==3:
            volumes.append(sum(b.volume for b in matching))
    out['evidence'].update(relative_volume_method='LAST_3_COMPLETED_SLOTS_VS_SAME_SLOTS_PRIOR_UP_TO_20_SESSIONS',
                           relative_volume_prior_sessions=len(volumes),relative_volume_min_sessions=3)
    if len(volumes)<3:
        return stop('TIME_MATCHED_RELATIVE_VOLUME_HISTORY_UNAVAILABLE','DATA_UNAVAILABLE')
    rel=D(sum(b.volume for b in current[-3:]))/(D(sum(volumes))/D(len(volumes)))
    vwaps=session_vwap(current); slope=(vwaps[-1]-vwaps[-3])/D(2)
    atr=D(str(indicators.atr14)); p=current[-1].close
    sides=[1 if b.close>v else -1 if b.close<v else 0 for b,v in zip(current,vwaps)]
    nonzero=[x for x in sides[-6:] if x]
    crosses=sum(x!=y for x,y in zip(nonzero,nonzero[1:]))
    out['evidence'].update(price=str(p),vwap=str(vwaps[-1]),vwap_slope=str(slope),
        vwap_slope_atr_per_bar=str(slope/atr),relative_volume_at_time=str(rel),
        inherited_relative_volume=str(indicators.relative_volume),adx14=indicators.adx14,
        chop14=indicators.chop14,atr14=str(atr),vwap_crosses_last_6=crosses)
    bull=all(b.close>high and b.close>v for b,v in zip(current[-2:],vwaps[-2:])) and slope>0
    bear=all(b.close<low and b.close<v for b,v in zip(current[-2:],vwaps[-2:])) and slope<0
    if bull or bear:
        if rel<1:
            return stop('BREAKOUT_PARTICIPATION_NOT_CONFIRMED')
        out.update(status='SIGNAL_OBSERVED',direction='BULLISH' if bull else 'BEARISH',
                   reason='OPENING_RANGE_BREAK_WITH_TWO_CLOSES_AND_VWAP_CONFIRMATION',
                   candidate_option_types=['put'] if bull else ['call'],
                   strategies=['PUT_CREDIT_SPREAD'] if bull else ['CALL_CREDIT_SPREAD'])
        return out
    if observed.time().replace(tzinfo=None)<time(10) or len(current)<6:
        return stop('CONDOR_NOT_BEFORE_0900_CT')
    # A recent break invalidates neutral classification even when ADX/CHOP lag.
    if any(not low<=b.close<=high for b in current[-3:]):
        return stop('RECENT_OPENING_RANGE_BREAK_TRANSITION')
    if abs(current[-1].close-current[-1].open)>D('1.5')*atr:
        return stop('RECENT_PRICE_EXPANSION_TRANSITION')
    tolerance=min((high-low)/D(4), D('.15')*atr)
    post=current[3:]
    lower=any(b.low<=low+tolerance and b.close>low+tolerance for b in post)
    upper=any(b.high>=high-tolerance and b.close<high-tolerance for b in post)
    out['evidence'].update(lower_boundary_rejection=lower,upper_boundary_rejection=upper,
                           boundary_tolerance=str(tolerance))
    if not (indicators.adx14<=20 and indicators.chop14>=55):
        return stop('RANGE_INDICATORS_NOT_CONFIRMED')
    if abs(slope)>D('.10')*atr or crosses<2 or not (lower and upper):
        return stop('TWO_SIDED_RANGE_AND_FLAT_VWAP_NOT_CONFIRMED')
    out.update(status='SIGNAL_OBSERVED',direction='NEUTRAL',reason='DEFENDED_RANGE_CONFIRMED',
               candidate_option_types=['put','call'],strategies=['IRON_CONDOR'])
    return out
