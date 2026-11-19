"""Barney EOD: cash settlement is distinct from an actual closing trade."""
import json
from copy import deepcopy
from datetime import datetime,date,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from option_bot.post_session import cash_expiration_payoff,fetch_cboe_closing_history,sweep_and_reconcile
from option_bot.local_paper import FLAGS,_atomic

ET=ZoneInfo('America/New_York')
NOW=datetime(2026,11,19,17,5,tzinfo=ET)

def condor(*,opened=True,expiry='2026-11-18'):
    legs=[('PUT','SELL',7230),('PUT','BUY',7225),('CALL','SELL',7435),('CALL','BUY',7440)]
    p={**FLAGS,'position_id':'X1','symbol':'SPX','status':'OPEN' if opened else 'EXPIRED',
      'opened_at':expiry+'T10:00:00-05:00','closed_at':None if opened else expiry+'T16:00:00-05:00',
      'premium_type':'CREDIT','entry_price':'0.45','quantity':1,'realized_pnl':None,
      'product':{'settlement_type':'CASH','exercise_style':'EUROPEAN','multiplier':100},
      'legs':[{'right':r,'side':s,'strike':str(k),'quantity':1,'expiration':expiry} for r,s,k in legs]}
    if not opened:p['settlement_status']='PENDING'
    return p

def test_cboe_close_parsing_never_uses_spot_or_future_timestamp():
    d={'timestamp':'2026-11-19 19:09:22','data':[{'date':'2026-11-18','close':'7323.63'}]}
    a,proof=fetch_cboe_closing_history(fetch=lambda url:d)
    assert a[date(2026,11,18)]==Decimal('7323.63')
    assert proof['source']=='CBOE_PUBLISHED_SPX_DAILY_CLOSE'

def test_intrinsic_payoff_calculates_upside_and_downside_exactly():
    p=condor()
    assert cash_expiration_payoff(p,Decimal('7323.63'))['pnl_usd']=='45.00'
    assert cash_expiration_payoff(p,Decimal('7230'))['pnl_usd']=='45.00'
    assert cash_expiration_payoff(p,Decimal('7228'))['pnl_usd']=='-155.00'
    assert cash_expiration_payoff(p,Decimal('7437'))['pnl_usd']=='-155.00'
    assert cash_expiration_payoff(p,Decimal('7441'))['pnl_usd']=='-455.00'

def test_post_session_reconciles_expired_0dte_with_exchange_level_and_is_idempotent(tmp_path):
    l=tmp_path/'paper.json';report=tmp_path/'eod.json'
    _atomic(l,{'schema_version':'1.0',**FLAGS,'open':[condor()], 'completed':[], 'events':[]})
    evidence={date(2026,11,18):Decimal('7323.63')}
    proof={'source':'CBOE_PUBLISHED_SPX_DAILY_CLOSE','url':'https://cdn.cboe.com/test', 'published_at_utc':'2026-11-19T19:09:22+00:00'}
    a,j=sweep_and_reconcile(l,report,NOW,history=evidence,provenance=proof)
    assert not j['open'];assert len(j['completed'])==1
    p=j['completed'][0]
    assert p['status']=='EXPIRED'
    assert p['settlement_status']=='RECONCILED_CBOE_CLOSE'
    assert p['realized_pnl']=='45.00'
    assert p['exit_fills']==[]
    assert [e['action'] for e in a['new_events']]==['PAPER_EXPIRE','PAPER_CASH_SETTLE']
    assert a['settlement_pending_count']==0
    b,j=sweep_and_reconcile(l,report,NOW,history=evidence,provenance=proof)
    assert len(j['events'])==2
    assert b['new_events']==[]

def test_missing_exchange_close_alerts_with_pending_pnl_and_no_false_sale(tmp_path):
    l=tmp_path/'paper.json';report=tmp_path/'eod.json'
    _atomic(l,{'schema_version':'1.0',**FLAGS,'open':[condor()], 'completed':[], 'events':[]})
    a,j=sweep_and_reconcile(l,report,NOW,history={},provenance={'source':'CBOE_PUBLISHED_SPX_DAILY_CLOSE'})
    assert not j['open'];assert a['settlement_pending_count']==1
    assert a['status']=='SETTLEMENT_PENDING_ATTENTION'
    assert j['completed'][0]['realized_pnl'] is None
    assert j['completed'][0]['exit_fills']==[]
    assert len([e for e in j['events'] if e['action']=='PAPER_CASH_SETTLE'])==0

def test_open_unexpired_position_not_closed_by_eod(tmp_path):
    l=tmp_path/'paper.json';report=tmp_path/'eod.json'
    p=condor(expiry='2026-11-20');p['position_id']='FUTURE'
    _atomic(l,{'schema_version':'1.0',**FLAGS,'open':[p], 'completed':[], 'events':[]})
    a,j=sweep_and_reconcile(l,report,NOW,history={})
    assert len(j['open'])==1 and a['open_positions']==1
    assert not a['new_events']

def test_executed_close_and_cash_expiry_shown_separately(tmp_path):
    l=tmp_path/'paper.json';report=tmp_path/'eod.json'
    closed=condor(opened=False);closed.update(status='CLOSED',position_id='SOLD',
       closed_at='2026-11-19T15:15:00-05:00',realized_pnl='15.00',
       exit_reason='PROFIT_TARGET',exit_fills=[{'side':'BUY','price':'0.20'}]);closed.pop('settlement_status',None)
    expiry=condor(opened=False);expiry['position_id']='EXPIRED'
    _atomic(l,{'schema_version':'1.0',**FLAGS,'open':[], 'completed':[closed,expiry], 'events':[]})
    a,j=sweep_and_reconcile(l,report,NOW,history={date(2026,11,18):Decimal('7323.63')},provenance={'source':'CBOE_PUBLISHED_SPX_DAILY_CLOSE'})
    assert len(a['executed_closing_trades_today'])==1
    assert len(a['cash_settled_expirations_today'])==0
    assert a['cumulative_realized_pnl_usd']=='60.00'
