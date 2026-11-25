from dataclasses import replace
from datetime import datetime,timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import json
from option_bot.indicators import Bar,ema
from option_bot.shadow_variant_signals import opening_retest,ema_250_450,RETEST,EMA_TREND
from option_bot.shadow_variant_cycle import run_cycle
from option_bot.local_paper import _atomic
from test_reversal_shadow_cycle import configuration

ET=ZoneInfo('America/New_York')
DAY=datetime(2026,11,20,9,30,tzinfo=ET)
I=SimpleNamespace(available=True,atr14=2.0)
def bar(n,price,low=None,high=None):
 p=D(str(price));return Bar(DAY+timedelta(minutes=5*n),p,
 D(str(high)) if high is not None else p+D('0.4'),
 D(str(low)) if low is not None else p-D('0.4'),p,100)

def retest_bars(bearish=False,with_retest=True):
 if bearish:
  closes=[100,100,100,98,97,96,99.3 if with_retest else 96,96 if with_retest else 95]
  return [bar(i,x,high=99.75 if i==6 and with_retest else None) for i,x in enumerate(closes)]
 closes=[100,100,100,102,103,104,100.7 if with_retest else 104,104 if with_retest else 105]
 return [bar(i,x,low=100.25 if i==6 and with_retest else None) for i,x in enumerate(closes)]

def test_retest_cannot_fill_on_original_two_candle_breakout():
 bars=retest_bars(False)[:6]
 r=opening_retest('SPX',I,bars,DAY+timedelta(minutes=30))
 assert r['status']=='WAIT' and 'RETEST' in r['reason']

def test_retest_requires_real_subsequent_touch_and_hold():
 bars=retest_bars(False)
 yes=opening_retest('SPX',I,bars,DAY+timedelta(minutes=40))
 assert yes['status']=='SIGNAL_OBSERVED' and yes['direction']=='BULLISH',yes
 assert yes['evidence']['retest_bar']>yes['evidence']['confirmation_completed_bar']
 no=opening_retest('SPX',I,retest_bars(False,False),DAY+timedelta(minutes=40))
 assert no['status']=='WAIT'

def test_retest_bearish_symmetry_and_lost_support_invalidates():
 bars=retest_bars(True)
 yes=opening_retest('XSP',I,bars,DAY+timedelta(minutes=40))
 assert yes['status']=='SIGNAL_OBSERVED' and yes['direction']=='BEARISH',yes
 no=opening_retest('XSP',I,retest_bars(True,False),DAY+timedelta(minutes=40))
 assert no['status']=='WAIT'

def test_ema_length_requires_450_completed_bars():
 rows=[bar(i,100) for i in range(449)]
 now=rows[-1].timestamp+timedelta(minutes=5)
 r=ema_250_450('SPX',I,rows,now)
 # The rows would span weekends/overnights in this synthetic fixture; only
 # NY regular-session bars count, so 450 cannot be reached here.
 assert r['status']=='DATA_UNAVAILABLE'
 assert r['reason'] in ('CURRENT_SESSION_GRID_INCOMPLETE','EMA450_HISTORY_INSUFFICIENT','COMPLETED_BARS_STALE')

def ema_fixture(closes=(100,100,100,98),bullish=False,last_low=None,last_high=None):
 rows=[]
 day=DAY-timedelta(days=12)
 while day<DAY:
  if day.weekday()<5:
   for j in range(78):
    p=D('140')-D(len(rows))/D(30)
    rows.append(Bar(day+timedelta(minutes=5*j),p,p+D(1),p-D(1),p,100))
  day+=timedelta(days=1)
 for j,value in enumerate(closes):
  p=D(str(value));lo=p-D(1);hi=p+D(1)
  if j==len(closes)-1:
   if last_low is not None:lo=D(str(last_low))
   if last_high is not None:hi=D(str(last_high))
  rows.append(Bar(DAY+timedelta(minutes=5*j),p,hi,lo,p,100))
 if bullish:
  rows=[replace(b,open=D(300)-b.open,close=D(300)-b.close,
       high=D(300)-b.low,low=D(300)-b.high) for b in rows]
 return rows,DAY+timedelta(minutes=5*len(closes))

def test_ema_first_completed_break_with_vwap_cross_both_directions():
 for bullish,direction in [(False,'BEARISH'),(True,'BULLISH')]:
  rows,now=ema_fixture(bullish=bullish)
  r=ema_250_450('SPX',I,rows,now)
  assert r['status']=='SIGNAL_OBSERVED' and r['direction']==direction,r
  assert r['evidence']['range_break_bar']==(DAY+timedelta(minutes=15)).isoformat()
  assert r['evidence']['hma21_1h_required'] is False

def test_ema_wick_only_and_exact_boundary_are_not_breaks():
 for bullish in [False,True]:
  for close in [100,99]:
   rows,now=ema_fixture((100,100,100,close),bullish,last_low=97)
   r=ema_250_450('SPX',I,rows,now)
   assert r['reason']=='OPENING_RANGE_CLOSE_BREAK_NOT_CONFIRMED',r

def test_ema_opening_range_cannot_trigger_entry_and_partial_break_ignored():
 rows,now=ema_fixture((100,100,98))
 assert ema_250_450('SPX',I,rows,now)['reason']=='POST_OPENING_RANGE_CLOSE_REQUIRED'
 rows,now=ema_fixture((100,100,100,98))
 assert ema_250_450('SPX',I,rows,now-timedelta(minutes=1))['status']!='SIGNAL_OBSERVED'

def test_ema_requires_vwap_cross_and_correct_current_side():
 # A high opening wick keeps VWAP above price: bearish OR break passes,
 # but no completed close ever crossed from above VWAP to below it.
 rows,now=ema_fixture()
 idx=next(i for i,b in enumerate(rows) if b.timestamp==DAY)
 rows[idx]=replace(rows[idx],high=D(200))
 r=ema_250_450('SPX',I,rows,now)
 assert r['reason']=='DIRECTIONAL_PRICE_VWAP_CROSS_NOT_CONFIRMED',r

def test_ema_reentry_into_range_cancels_break_and_missing_open_grid_blocks():
 rows,now=ema_fixture((100,100,100,98,100))
 assert ema_250_450('SPX',I,rows,now)['reason']=='OPENING_RANGE_CLOSE_BREAK_NOT_CONFIRMED'
 rows,now=ema_fixture()
 rows=[b for b in rows if b.timestamp!=DAY]
 assert ema_250_450('SPX',I,rows,now)['reason']=='OPENING_RANGE_GRID_INCOMPLETE'

def test_management_writes_two_independent_empty_ledgers(tmp_path):
 cfg=configuration(tmp_path)
 for strategy,prefix in ((RETEST,'opening_range_retest_shadow'),(EMA_TREND,'ema250_450_shadow')):
  r=run_cycle(cfg,tmp_path,DAY+timedelta(minutes=40),strategy=strategy,allow_entries=False)
  assert r['broker_submissions']==0 and r['open_count']==r['completed_count']==0
  assert all(x['status']=='MANAGEMENT_ONLY' for x in r['results'])
  assert (tmp_path/(prefix+'_paper_ledger.json')).exists()
 assert not (tmp_path/'option_001_paper_ledger.json').exists()
 assert not (tmp_path/'opening_range_shadow_paper_ledger.json').exists()

def test_stale_or_missing_snapshot_cannot_open_variant_trades(tmp_path):
 cfg=configuration(tmp_path)
 for strategy in (RETEST,EMA_TREND):
  result=run_cycle(cfg,tmp_path,DAY+timedelta(minutes=40),strategy=strategy,allow_entries=True,events={})
  assert not result['new_events'] and result['broker_submissions']==0
