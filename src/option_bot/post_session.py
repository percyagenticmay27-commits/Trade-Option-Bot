"""Barney post-session paper expiry, exchange-close evidence and EOD audit.

Cash-settled expiration is never a closing fill. The exchange-published SPX
PM daily closing index value supports an expiration payoff, but is not a
broker-cleared account confirmation. No network data can create an order.
"""
from __future__ import annotations
import fcntl
import json
import urllib.request
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo
from option_bot.session_expiration import expired_session_close
from option_bot.local_paper import _atomic, _decimal, FLAGS

ET=ZoneInfo('America/New_York')
CBOE_HISTORY_URL='https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/_SPX.json'


def fetch_cboe_closing_history(*, fetch=None):
    if fetch is None:
        def fetch(url):
            req=urllib.request.Request(url,headers={'User-Agent':'Option-001-paper-reconciliation/1.0','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=12) as res:
                if res.status!=200:raise ValueError('CBOE_HTTP_STATUS_'+str(res.status))
                if len(res.headers.get('content-length','0'))>12000000:raise ValueError('CBOE_PAYLOAD_TOO_LARGE')
                return json.load(res)
    payload=fetch(CBOE_HISTORY_URL)
    if not isinstance(payload,dict) or not isinstance(payload.get('timestamp'),str) or not isinstance(payload.get('data'),list):
        raise ValueError('CBOE_PUBLISHED_HISTORY_INVALID')
    # Cboe's daily OHLC history includes exchange publication time and a date
    # indexed close. Never use a current spot quote as historical settlement.
    published=datetime.fromisoformat(payload['timestamp'].replace('Z','+00:00'))
    if published.tzinfo is None:published=published.replace(tzinfo=timezone.utc)
    if published>datetime.now(timezone.utc):raise ValueError('CBOE_FUTURE_PUBLICATION')
    values={}
    for row in payload['data']:
        if not isinstance(row,dict):continue
        try:
            day=date.fromisoformat(row['date'])
            close=_decimal(row['close'])
            if close<=0:continue
            if day in values and values[day]!=close:raise ValueError('CBOE_CONFLICTING_CLOSE')
            values[day]=close
        except (KeyError,TypeError,InvalidOperation):continue
    return values, {'source':'CBOE_PUBLISHED_SPX_DAILY_CLOSE',
                    'url':CBOE_HISTORY_URL,'published_at_utc':published.astimezone(timezone.utc).isoformat()}


def cash_expiration_payoff(position,close):
    if position.get('symbol')!='SPX':raise ValueError('SETTLEMENT_PROVIDER_UNSUPPORTED_SYMBOL')
    product=position.get('product') or {}
    if product.get('settlement_type')!='CASH' or product.get('exercise_style')!='EUROPEAN':
        raise ValueError('CASH_EUROPEAN_POSITION_REQUIRED')
    mult=_decimal(product['multiplier']);qty=_decimal(position.get('quantity',1))
    expiry={l['expiration'] for l in position['legs']}
    if len(expiry)!=1:raise ValueError('MIXED_EXPIRATIONS_UNSUPPORTED')
    if close<=0 or not close.is_finite():raise ValueError('INVALID_CBOE_CLOSE')
    intrinsic=Decimal(0)
    for leg in position['legs']:
        strike=_decimal(leg['strike'])
        right=leg['right'].upper()
        if right not in ('PUT','CALL'):raise ValueError('UNKNOWN_RIGHT')
        if leg['side'] not in ('BUY','SELL'):raise ValueError('UNKNOWN_SIDE')
        value=max(Decimal(0),strike-close if right=='PUT' else close-strike)
        intrinsic+=(Decimal(1) if leg['side']=='BUY' else Decimal(-1))*value*_decimal(leg.get('quantity',1))
    settlement_cash=intrinsic*mult
    initial=_decimal(position['entry_price'])*qty*mult
    pnl=(initial+settlement_cash if position['premium_type']=='CREDIT' else -initial+settlement_cash)
    return {'closing_index':str(close),'expiration_cashflow_usd':str(settlement_cash.quantize(Decimal('.01'))),
            'opening_premium_usd':str(initial.quantize(Decimal('.01'))),
            'pnl_usd':str(pnl.quantize(Decimal('.01')))}


def sweep_and_reconcile(ledger_path:Path,report_path:Path,now:datetime,*,history=None,provenance=None):
    if now.tzinfo is None:raise ValueError('AWARE_TIME_REQUIRED')
    ledger_path=Path(ledger_path);report_path=Path(report_path)
    ledger_path.parent.mkdir(parents=True,exist_ok=True)
    with ledger_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'schema_version':'1.0',**FLAGS,'open':[],'completed':[],'events':[]}
        if state.get('paper_only') is not True:raise ValueError('NON_PAPER_LEDGER')
        events=[]
        for position in list(state['open']):
            close_at=expired_session_close(position,now)
            if close_at is None:continue
            position.update(status='EXPIRED',closed_at=close_at.isoformat(),
                expiration_processed_at=now.astimezone(ET).isoformat(),
                exit_price=None,current_price=None,unrealized_pnl=None,realized_pnl=None,
                settlement_status='PENDING',settlement_reason='CBOE_PM_EXPIRATION_CLOSE_REQUIRED',
                exit_reason='NY_SESSION_CLOSE_PAPER_EXPIRATION',exit_fills=[],exit_pending=False)
            state['open'].remove(position);state['completed'].append(position)
            event={**FLAGS,'action':'PAPER_EXPIRE','position_id':position['position_id'],
                'symbol':position['symbol'],'observed_at':now.astimezone(ET).isoformat(),
                'effective_at':close_at.isoformat(),'settlement_status':'PENDING','realized_pnl':None,
                'fills':[],'reason':'NY_SESSION_CLOSE_PAPER_EXPIRATION'}
            state['events'].append(event);events.append(event)
        pending=[p for p in state['completed'] if p.get('settlement_status')=='PENDING']
        if pending and history is None:
            try:history,provenance=fetch_cboe_closing_history()
            except (OSError,ValueError,TimeoutError,TypeError) as exc:
                history={};provenance={'source':'CBOE_PUBLISHED_SPX_DAILY_CLOSE','error':type(exc).__name__+':'+str(exc)[:180]}
        history=history or {}
        provenance=provenance or {'source':'INJECTED_TEST_EXCHANGE_HISTORY'}
        for p in pending:
            try:
                expiry={date.fromisoformat(l['expiration']) for l in p['legs']}
                if len(expiry)!=1:raise ValueError('MIXED_EXPIRATIONS_UNSUPPORTED')
                day=next(iter(expiry))
                if day>now.astimezone(ET).date():raise ValueError('PRE_EXPIRY_CANNOT_SETTLE')
                if day not in history:raise ValueError('CBOE_EXPIRATION_CLOSE_UNAVAILABLE')
                close=_decimal(history[day]);econ=cash_expiration_payoff(p,close)
            except (ValueError,TypeError,KeyError,ArithmeticError,InvalidOperation) as exc:
                p['settlement_reason']=str(exc)
                p['settlement_last_checked_at']=now.isoformat()
                continue
            p.update(realized_pnl=econ['pnl_usd'],settlement_status='RECONCILED_CBOE_CLOSE',
                settlement_reason='EXCHANGE_PUBLISHED_PM_CLOSE_AWAITING_BROKER_CASH_CONFIRMATION',
                settlement_close_level=econ['closing_index'],
                settlement_cashflow_usd=econ['expiration_cashflow_usd'],
                settlement_opening_premium_usd=econ['opening_premium_usd'],
                settlement_source=provenance['source'],settlement_source_url=provenance.get('url'),
                settlement_source_published_at=provenance.get('published_at_utc'),
                settlement_reconciled_at=now.isoformat(),exit_fills=[])
            event={**FLAGS,'action':'PAPER_CASH_SETTLE','position_id':p['position_id'],
                'symbol':p['symbol'],'observed_at':now.astimezone(ET).isoformat(),
                'settlement_value':econ['closing_index'],'realized_pnl':econ['pnl_usd'],
                'reason':'CBOE_PUBLISHED_PM_EXPIRATION_CLOSE','fills':[]}
            state['events'].append(event);events.append(event)
        if events or any(p.get('settlement_last_checked_at')==now.isoformat() for p in pending):
            state['generated_at_utc']=now.astimezone(ET).isoformat()
            _atomic(ledger_path,state)
        unresolved=[{'id':p['position_id'],'symbol':p['symbol'],
                     'expiry':max(l['expiration'] for l in p['legs']),
                     'reason':p.get('settlement_reason','SOURCE_UNAVAILABLE')}
                    for p in state['completed'] if p.get('settlement_status')=='PENDING']
        latest_date=now.astimezone(ET).date().isoformat()
        recent=[p for p in state['completed'] if (p.get('closed_at') or '').startswith(latest_date)]
        report={'schema_version':'1.0','report_generated_at':now.isoformat(),
            'trade_date_et':latest_date,'status':'SETTLEMENT_PENDING_ATTENTION' if unresolved else 'RECONCILED',
            'paper_only':True,'broker_submissions':0,
            'open_positions':len(state['open']),
            'expired_open_positions':sum(e['action']=='PAPER_EXPIRE' for e in events),
            'executed_closing_trades_today':[{'id':p['position_id'],'symbol':p['symbol'],'realized_pnl':p.get('realized_pnl'),
                                              'exit_reason':p.get('exit_reason'),'exit_fills':p.get('exit_fills',[])}
                                             for p in recent if p.get('status')=='CLOSED'],
            'cash_settled_expirations_today':[{'id':p['position_id'],'symbol':p['symbol'],
                 'status':p.get('settlement_status'),'realized_pnl':p.get('realized_pnl'),
                 'closing_index':p.get('settlement_close_level')}
                  for p in recent if p.get('status')=='EXPIRED'],
            'settlement_reconciled_total':sum(p.get('settlement_status')=='RECONCILED_CBOE_CLOSE' for p in state['completed']),
            'settlement_pending_count':len(unresolved),'settlement_pending_alerts':unresolved,
            'cumulative_realized_pnl_usd':str(sum((_decimal(p['realized_pnl']) for p in state['completed'] if p.get('realized_pnl') is not None),Decimal(0)).quantize(Decimal('.01'))),
            'new_events':events,'settlement_evidence':provenance,
            'broker_confirmation_required':True}
        _atomic(report_path,report)
        return report,state
