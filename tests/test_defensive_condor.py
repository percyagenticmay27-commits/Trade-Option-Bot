from datetime import datetime
from decimal import Decimal as D
from option_bot.defensive_condor import candidates
from option_bot.local_paper import _candidate

def date(h):return datetime.fromisoformat(f'2026-11-11T{h}:00-06:00')
def position():
 return {'symbol':'XSP','trade_date':'2026-11-11','structure':'CALL_CREDIT_SPREAD',
  'premium_type':'CREDIT','entry_price':'0.70','current_price':'1.75',
  'maximum_loss':'430.00','product':{'multiplier':100,'exercise_style':'EUROPEAN','settlement_type':'CASH','last_trading_time':'16:00'},
  'candidate_id':'test','legs':[{'contract_symbol':'c100','instrument_id':'c100','right':'CALL','side':'SELL','strike':'100','expiration':'2026-11-11','quantity':1},
  {'contract_symbol':'c105','instrument_id':'c105','right':'CALL','side':'BUY','strike':'105','expiration':'2026-11-11','quantity':1}]}
def doc():
 return {'symbols':{'XSP':{'contracts':[{'symbol':n,'instrument_id':n,'state':'active','tradability':'tradable','type':'put','expiration_date':'2026-11-11','strike_price':k,'quote':{'delta':d}} for n,k,d in [('p90','90','-.13'),('p85','85','-.04')]]}}}
def q(candidate,doc,now):
 from option_bot.domain import TradeSide
 fills=[{'instrument_id':x.contract_symbol,'price':'0.28' if x.side is TradeSide.SELL else '0.05','simulated':True} for x in candidate.legs]
 return D('-0.23'),fills,{}
def test_defense_candidate_is_defined_risk_and_reduces_max_loss():
 c=candidates(position(),doc(),date('11:25'),q,_candidate,D(500))
 assert c and c['credit']==D('.23') and c['max_risk']==D('407.00')
 assert c['profile'].maximum_profit.amount==D('93.00')
def test_outside_cutoff_no_adjustment():
 assert candidates(position(),doc(),date('12:30'),q,_candidate,D(500)) is None
 assert candidates(position(),doc(),date('09:59'),q,_candidate,D(500)) is None
def test_duplicate_defense_forbidden():
 p=position();p['defensive_adjustment']={'filled':True}
 assert candidates(p,doc(),date('11:25'),q,_candidate,D(500)) is None
def test_stop_already_crossed_does_not_defend():
 p=position();p['current_price']='3.00'
 assert candidates(p,doc(),date('11:25'),q,_candidate,D(500)) is None
def test_wrong_side_or_expiration_does_not_defend():
 d=doc();d['symbols']['XSP']['contracts'][0]['expiration_date']='2026-11-12'
 assert candidates(position(),d,date('11:25'),q,_candidate,D(500)) is None

def test_active_manager_paper_defense_converts_and_preserves_stop(monkeypatch,tmp_path):
 from types import SimpleNamespace
 from datetime import time
 from option_bot.local_paper import LocalPaperSimulation
 cfg=SimpleNamespace(paper_only=True,order_submission_enabled=False,
  database_path=tmp_path/'trades.sqlite3',mandatory_exit=time(15,30),
  max_daily_defined_loss=D('500'),entry_start=time(9,45),entry_end=time(12,0),
  loss_limit_for=lambda symbol:D('500'))
 sim=LocalPaperSimulation(cfg)
 p=position();p.update(paper_only=True,order_submission_enabled=False,position_id='TEST',opened_at='2026-11-11T11:00:00-06:00',
                     status='OPEN',entry_fills=[],entry_short_deltas=[{'instrument_id':'c100','delta':'.18','strike':'100'}],
                     exposure_group='SPX_XSP_INDEX')
 state={'schema_version':'1.0','paper_only':True,'open':[p], 'completed':[],'events':[]}
 d=doc();d.update(source='ROBINHOOD_MCP_RESEARCH',research_only=True,
  order_submission_enabled=False,generated_at_utc=date('11:25').isoformat())
 def quote(candidate,document,now,closing=False,held_legs=None):
  ids={l.contract_symbol for l in candidate.legs}
  if ids=={'c100','c105'}:return D('-1.75'),[],{}
  if ids=={'p90','p85'}:
   return (D('-.23'),[{'instrument_id':'p90','side':'SELL','price':'.28','simulated':True},
                    {'instrument_id':'p85','side':'BUY','price':'.05','simulated':True}],
                   {'p90':{'instrument_id':'p90'},'p85':{'instrument_id':'p85'}})
  assert ids=={'c100','c105','p90','p85'}
  return (D('-3.10') if now.minute==26 else D('-1.98')),[],{}
 monkeypatch.setattr('option_bot.local_paper._quote_legs',quote)
 result=sim._cycle(state,(),d,date('11:25'),allow_entries=False,force_close=False,force_expiry_holds=False)
 assert len(result['open'])==1 and result['open'][0]['structure']=='IRON_CONDOR'
 assert result['open'][0]['maximum_loss']=='407.00'
 assert result['open'][0]['defensive_adjustment']['status']=='PAPER_FILLED'
 assert len([e for e in result['new_events'] if e['action']=='PAPER_DEFENSIVE_ADJUST'])==1
 assert result['open'][0]['paper_only'] and not result['open'][0]['order_submission_enabled']
 # Re-entry is impossible: one-time mark persists after another management cycle.
 result2=sim._cycle(state,(),d,date('11:26'),allow_entries=False,force_close=False,force_expiry_holds=False)
 assert not any(e['action']=='PAPER_DEFENSIVE_ADJUST' for e in result2['new_events'])
 assert len(result2['open'])==0 and result2['completed'][0]['exit_reason']=='HALF_MAX_LOSS'
 assert result2['completed'][0]['realized_pnl']=='-217.00'
