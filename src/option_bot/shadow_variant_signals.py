"""Pure signals for two new, separately ledgered OPTION-001 paper shadows.

Only completed NY regular-session five-minute bars are eligible. The source
underlying is SPY for both SPX and XSP; trend checks never authorize fills.
"""
from datetime import timedelta, time
from decimal import Decimal as D
from zoneinfo import ZoneInfo
from option_bot.indicators import ema,session_vwap
from option_bot.opening_range_shadow import evaluate as opening_evaluate

ET=ZoneInfo('America/New_York')
RETEST='OPENING_RANGE_BREAKOUT_RETEST_SHADOW_V1'
EMA_TREND='EMA250_EMA450_5M_SHADOW_V1'

def _base(strategy,symbol,now):
 return dict(strategy=strategy,symbol=symbol,at=now.isoformat(),status='DATA_UNAVAILABLE',
             direction=None,reason='BARS_UNAVAILABLE',evidence={},paper_only=True,broker_submissions=0)

def _bars(bars,now):
 return tuple(sorted((b for b in bars if b.timestamp.tzinfo is not None
     and b.timestamp+timedelta(minutes=5)<=now and
     time(9,30)<=b.timestamp.astimezone(ET).time().replace(tzinfo=None)<time(16)),
     key=lambda b:b.timestamp))

def _valid(rows,now):
 if not rows:return 'CURRENT_COMPLETED_5M_BARS_UNAVAILABLE'
 today=[b for b in rows if b.timestamp.astimezone(ET).date()==now.astimezone(ET).date()]
 if not today:return 'CURRENT_SESSION_BARS_UNAVAILABLE'
 if now-(today[-1].timestamp+timedelta(minutes=5))>timedelta(minutes=5):
  return 'COMPLETED_BARS_STALE'
 if any(b.volume<=0 or b.low<=0 or b.low>min(b.open,b.close) or b.high<max(b.open,b.close) for b in rows):
  return 'INVALID_OHLC_OR_VOLUME'
 if any(y.timestamp-x.timestamp!=timedelta(minutes=5) for x,y in zip(today,today[1:])):
  return 'CURRENT_SESSION_GRID_INCOMPLETE'
 return None

def opening_retest(symbol,indicators,bars,now):
 out=_base(RETEST,symbol,now)
 if now.tzinfo is None:out['reason']='TIMEZONE_REQUIRED';return out
 rows=_bars(bars,now);problem=_valid(rows,now)
 if problem:out['reason']=problem;return out
 today=[b for b in rows if b.timestamp.astimezone(ET).date()==now.astimezone(ET).date()]
 if len(today)<6:out.update(status='WAIT',reason='RETEST_NOT_YET_AVAILABLE');return out
 expected=[time(9,30),time(9,35),time(9,40)]
 if [b.timestamp.astimezone(ET).time().replace(tzinfo=None) for b in today[:3]]!=expected:
  out['reason']='OPENING_RANGE_GRID_INCOMPLETE';return out
 if not indicators.available or indicators.atr14<=0:
  out['reason']='INDICATOR_WARMUP_UNAVAILABLE';return out
 high=max(x.high for x in today[:3]);low=min(x.low for x in today[:3])
 vwap=session_vwap(today)
 atr=D(str(indicators.atr14))
 tolerance=min((high-low)/D(4),D('0.15')*atr)
 out['evidence'].update(opening_range_high=str(high),opening_range_low=str(low),
     retest_tolerance=str(tolerance),last_completed_bar=today[-1].timestamp.isoformat(),
     current_close=str(today[-1].close),vwap=str(vwap[-1]))
 # Never allow the original two-close breakout itself to count as a retest.
 # The retest must occur on a subsequent completed candle that touches the
 # old range boundary and then closes back on the breakout side of it.
 for side,bound in [('BULLISH',high),('BEARISH',low)]:
  for i in range(4,len(today)-1):
   first,second=today[i-1],today[i]
   confirmed=(first.close>high and second.close>high and
              first.close>vwap[i-1] and second.close>vwap[i]) if side=='BULLISH' else (
              first.close<low and second.close<low and
              first.close<vwap[i-1] and second.close<vwap[i])
   if not confirmed:continue
   # Only recent retests; never reuse an old intraday touch as a new signal.
   for j in range(max(i+1,len(today)-2),len(today)):
    touch=today[j]
    holds=(bound-tolerance<=touch.low<=bound+tolerance and touch.close>bound) if side=='BULLISH' else (
           bound-tolerance<=touch.high<=bound+tolerance and touch.close<bound)
    # No intervening violation since confirmation; invalidated setups cannot revive.
    intervening=today[i+1:j]
    intact=all(b.close>bound for b in intervening) if side=='BULLISH' else all(b.close<bound for b in intervening)
    current=today[-1]
    still_valid=(current.close>bound and current.close>vwap[-1]) if side=='BULLISH' else (
                 current.close<bound and current.close<vwap[-1])
    if holds and intact and still_valid:
     out.update(status='SIGNAL_OBSERVED',direction=side,reason='CONFIRMED_BREAKOUT_RETEST_AND_HOLD',
         candidate_option_types=['put'] if side=='BULLISH' else ['call'],
         strategies=['PUT_CREDIT_SPREAD'] if side=='BULLISH' else ['CALL_CREDIT_SPREAD'])
     out['evidence'].update(confirmation_completed_bar=today[i].timestamp.isoformat(),
         retest_bar=touch.timestamp.isoformat(),retest_touch=str(touch.low if side=='BULLISH' else touch.high))
     return out
 out.update(status='WAIT',reason='BREAKOUT_RETEST_SUPPORT_OR_RESISTANCE_NOT_CONFIRMED')
 return out

def ema_250_450(symbol,indicators,bars,now):
 """EMA bias + completed opening-range break + session price/VWAP cross.

 VWAP may cross before or after the range break; both must remain valid.
 HMA21 and LIN12 do not authorize or block this version's entries.
 """
 out=_base(EMA_TREND,symbol,now)
 out['signal_rule_version']='EMA_OR15_VWAP_V2_20261125'
 if now.tzinfo is None:out['reason']='TIMEZONE_REQUIRED';return out
 rows=_bars(bars,now);problem=_valid(rows,now)
 if problem:out['reason']=problem;return out
 if len(rows)<450:
  out['reason']='EMA450_HISTORY_INSUFFICIENT'
  out['evidence']={'completed_bars':len(rows),'required_completed_bars':450}
  return out
 today=[b for b in rows if b.timestamp.astimezone(ET).date()==now.astimezone(ET).date()]
 if len(today)<3:
  out.update(status='WAIT',reason='OPENING_RANGE_NOT_COMPLETE');return out
 if [b.timestamp.astimezone(ET).time().replace(tzinfo=None) for b in today[:3]]!=[time(9,30),time(9,35),time(9,40)]:
  out['reason']='OPENING_RANGE_GRID_INCOMPLETE';return out
 ema250=ema([b.close for b in rows],250)
 ema450=ema([b.close for b in rows],450)
 direction='BULLISH' if ema250[-1]>ema450[-1] else 'BEARISH' if ema450[-1]>ema250[-1] else None
 current=today[-1];high=max(b.high for b in today[:3]);low=min(b.low for b in today[:3])
 vwaps=session_vwap(today)
 out['evidence'].update(ema250=str(ema250[-1]),ema450=str(ema450[-1]),
   ema250_prior=str(ema250[-2]),ema450_prior=str(ema450[-2]),
   price=str(current.close),last_completed_bar=current.timestamp.isoformat(),
   bars_used=len(rows),timeframe='5minute',trend=direction,
   opening_range_high=str(high),opening_range_low=str(low),vwap=str(vwaps[-1]),
   range_session='09:30-09:45 America/New_York',confirmation='COMPLETED_5MIN_CLOSE',
   vwap_cross_required=True,hma21_1h_required=False,lin12_required=False)
 if direction is None:out.update(status='WAIT',reason='EMAS_EQUAL_NO_TREND');return out
 out['direction']=direction
 if len(today)<4:
  out.update(status='WAIT',reason='POST_OPENING_RANGE_CLOSE_REQUIRED');return out
 bullish=direction=='BULLISH'
 outside=lambda b: b.close>high if bullish else b.close<low
 if not outside(current):
  out.update(status='WAIT',reason='OPENING_RANGE_CLOSE_BREAK_NOT_CONFIRMED');return out
 # Start of the current uninterrupted excursion outside the fixed range.
 first=len(today)-1
 while first>3 and outside(today[first-1]):first-=1
 out['evidence']['range_break_bar']=today[first].timestamp.isoformat()
 out['evidence']['range_break_close']=str(today[first].close)
 crosses=[i for i in range(1,len(today)) if (
   today[i-1].close<=vwaps[i-1] and today[i].close>vwaps[i]) ] if bullish else [
   i for i in range(1,len(today)) if today[i-1].close>=vwaps[i-1] and today[i].close<vwaps[i]]
 on_side=current.close>vwaps[-1] if bullish else current.close<vwaps[-1]
 if not crosses or not on_side:
  out.update(status='WAIT',reason='DIRECTIONAL_PRICE_VWAP_CROSS_NOT_CONFIRMED');return out
 out['evidence']['vwap_cross_bar']=today[crosses[-1]].timestamp.isoformat()
 out.update(status='SIGNAL_OBSERVED',reason='EMA_BIAS_OPENING_RANGE_CLOSE_BREAK_AND_VWAP_CROSS',
   candidate_option_types=['put'] if bullish else ['call'],
   strategies=['PUT_CREDIT_SPREAD'] if bullish else ['CALL_CREDIT_SPREAD'])
 return out
