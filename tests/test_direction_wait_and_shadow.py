from datetime import datetime,timezone
from dataclasses import replace
from decimal import Decimal as D
from option_bot.collection_policy import collection_plan
from option_bot.direction_wait import is_trend_wait
from option_bot.reversal_shadow import evaluate
from test_directional_gate import snapshot

NOW=datetime(2026,11,12,15,20,tzinfo=timezone.utc)

def conflicting():
 return replace(snapshot(),price=D('110'),vwap=D('100'),ema50=D('115'),ema50_slope=D('-.2'),
                ema9=D('107'),ema20=D('105'),relative_volume=D('1.4'),adx14=30,chop14=40)

def test_conflict_is_explicit_wait_not_missing_market_data():
 row=collection_plan(conflicting())
 assert row['status']=='WAIT_FOR_TREND_CONFIRMATION'
 assert row['candidate_option_types']==[] and row['bias'] is None

def test_fresh_plan_wait_requires_both_priority_symbols_and_actual_bar_evidence():
 plan={'source':'ROBINHOOD_MCP_RESEARCH','order_submission_enabled':False,
       'generated_at_et':NOW.isoformat(),'symbols':{s:{**collection_plan(conflicting()),
       'last_completed_bar':'2026-11-12T10:15:00-05:00'} for s in ('SPX','XSP')}}
 assert is_trend_wait(plan,NOW)
 plan['symbols']['SPX']['last_completed_bar']=None
 assert not is_trend_wait(plan,NOW)
 plan['symbols']['SPX']['last_completed_bar']='2026-11-12T10:15:00-05:00'
 assert not is_trend_wait(plan,NOW.replace(hour=17))

def test_shadow_observes_reversal_but_never_allows_paper_entry():
 out=evaluate('SPX',conflicting(),NOW)
 assert out['status']=='SIGNAL_OBSERVED' and out['direction']=='BULLISH'
 assert out['strict_ema50_would_allow'] is False
 assert out['paper_entries']==out['broker_submissions']==0
 assert out['pnl_status']=='NOT_MEASURABLE_NO_VERIFIED_FILLS'
