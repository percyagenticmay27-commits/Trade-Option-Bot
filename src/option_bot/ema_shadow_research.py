"""Dedicated EMA shadow research publication; never writes baseline artifacts.

Preserves provider timestamps. A current collection time does not make stale
bars or leg quotes current. Actual option validation stays in the paper engine.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from option_bot.local_paper import _atomic, _fresh
from option_bot.providers.robinhood_research import load_robinhood_research_bars
from option_bot.shadow_variant_signals import _bars, _valid

ET=ZoneInfo('America/New_York')
NAME='ema250_450_shadow_research.json'

def validate_document(document,now):
 if (document.get('source')!='ROBINHOOD_MCP_RESEARCH'
     or document.get('research_only') is not True
     or document.get('order_submission_enabled') is not False
     or any(document.get(k) is True for k in ('live_trading_enabled','broker_execution_enabled','order_placement_enabled'))):
  raise ValueError('EMA_RESEARCH_GOVERNANCE_INVALID')
 symbols=document.get('symbols',{})
 for symbol in ('SPX','XSP'):
  payload=symbols.get(symbol,{})
  if payload.get('bar_source_symbol')!='SPY':raise ValueError('EMA_SPY_BAR_SOURCE_REQUIRED:'+symbol)
  raw=payload.get('bars',[])
  if not isinstance(raw,list) or not raw:raise ValueError('EMA_SPY_BARS_REQUIRED:'+symbol)
  stamps=[]
  for bar in raw:
   ts=datetime.fromisoformat(str(bar['timestamp']).replace('Z','+00:00'))
   if ts.tzinfo is None:raise ValueError('EMA_BAR_TIMEZONE_REQUIRED')
   stamps.append(ts)
  if len(set(stamps))!=len(stamps):raise ValueError('EMA_DUPLICATE_BAR_TIMESTAMPS')
  # Validate OHLC through the actual provider loader after atomic publication;
  # strict row parsing here avoids silently accepting dropped malformed bars.
  from decimal import Decimal as D
  for bar in raw:
   o,h,l,c=[D(str(bar[k])) for k in ('open','high','low','close')]
   if (not all(x.is_finite() and x>0 for x in (o,h,l,c)) or
       l>min(o,c) or h<max(o,c) or int(bar['volume'])<=0):
    raise ValueError('EMA_INVALID_OHLC_OR_VOLUME')
  eligible=[ts for ts in stamps if ts+timedelta(minutes=5)<=now and
       (9,30)<=(ts.astimezone(ET).hour,ts.astimezone(ET).minute)<(16,0)]
  if len(eligible)<450:raise ValueError('EMA450_HISTORY_INSUFFICIENT:'+symbol)
 # The two index signals must be calculated from the same SPY candles.
 if symbols['SPX']['bars']!=symbols['XSP']['bars']:raise ValueError('EMA_PROXY_BAR_MISMATCH')

def publish(source,root,now):
 root=Path(root);source=Path(source)
 document=json.loads(source.read_text())
 validate_document(document,now)
 # No timestamp replacement and no contract synthesis/price interpolation.
 snapshot=copy.deepcopy(document)
 snapshot.update(paper_only=True,live_trading_enabled=False,broker_execution_enabled=False,
                 order_placement_enabled=False,shadow_strategy='EMA250_EMA450_5M_SHADOW_V1')
 _atomic(root/NAME,snapshot)
 return root/NAME

def health(root,now,attempts):
 root=Path(root);snapshot=root/NAME
 try:doc=json.loads(snapshot.read_text())
 except (OSError,ValueError):doc={}
 rows={};reasons=[]
 for symbol in ('SPX','XSP'):
  bars=_bars(load_robinhood_research_bars(snapshot,symbol),now)
  issue=_valid(bars,now)
  if len(bars)<450:issue='EMA450_HISTORY_INSUFFICIENT'
  contracts=(doc.get('symbols',{}).get(symbol,{}) or {}).get('contracts',[])
  quotes_fresh=bool(contracts) and all(_fresh(c.get('quote',{}).get('updated_at'),now) for c in contracts)
  rows[symbol]=dict(completed_regular_bars=len(bars),last_completed_bar=bars[-1].timestamp.isoformat() if bars else None,
    bars_status=issue or 'AVAILABLE',contract_count=len(contracts),option_quotes_fresh=quotes_fresh)
  if issue:reasons.append(issue)
  if not quotes_fresh:reasons.append('EMA_OPTION_QUOTES_REFRESH_REQUIRED')
 if not _fresh(doc.get('generated_at_utc'),now):reasons.append('EMA_PROVIDER_SNAPSHOT_REFRESH_REQUIRED')
 report=dict(checked_at_utc=now.isoformat(),snapshot_file=NAME,source_generated_at_utc=doc.get('generated_at_utc'),
  status='AVAILABLE' if not reasons else 'REFRESH_REQUIRED',reasons=sorted(set(reasons)),symbols=rows,
  input_attempts=attempts,paper_only=True,broker_submissions=0)
 _atomic(root/'ema250_450_shadow_research_health.json',report)
 # Keep a durable explicit collector request, rather than silently reading an
 # unrelated baseline management-only snapshot with zero signal candles.
 _atomic(root/'ema250_450_shadow_refresh_request.json',dict(report,
  status='RESOLVED' if not reasons else 'PENDING_PROVIDER_REFRESH',
  required_action='COLLECT_COMPLETED_SPY_5MIN_RTH_HISTORY_AND_CURRENT_DIRECTIONAL_INDEX_CONTRACT_QUOTES',
  required_history_bars=450,source_symbol='SPY',target_symbols=['SPX','XSP'],max_quote_age_seconds=60))
 return report

def refresh(root,now):
 root=Path(root);specific=root/NAME;attempts=[]
 # Honor the active provider handoff first; it may differ from the default
 # baseline file during a direction-wait or refresh/retry management cycle.
 sources=[os.environ.get('EMA250_450_RESEARCH_INPUT'),os.environ.get('ROBINHOOD_RESEARCH_SNAPSHOT_PATH'),
          str(root/'early_reversal_shadow_research.json'),str(root/'robinhood_option_research.json')]
 try:current=json.loads(specific.read_text()).get('generated_at_utc')
 except (OSError,ValueError):current=None
 candidates=[]
 for raw in dict.fromkeys(x for x in sources if x):
  path=Path(raw)
  if path.resolve()==specific.resolve():continue
  try:
   doc=json.loads(path.read_text());validate_document(doc,now)
   if not _fresh(doc.get('generated_at_utc'),now):raise ValueError('SOURCE_SNAPSHOT_STALE')
   stamp=datetime.fromisoformat(doc['generated_at_utc'].replace('Z','+00:00'))
   candidates.append((stamp,path));attempts.append(dict(source=str(path),status='VALID'))
  except (OSError,ValueError,TypeError,KeyError,ArithmeticError) as exc:
   attempts.append(dict(source=str(path),status='REJECTED',reason=str(exc)[:160]))
 if candidates:
  stamp,path=max(candidates,key=lambda x:x[0])
  previous=datetime.fromisoformat(current.replace('Z','+00:00')) if current else None
  if previous is None or stamp>previous:publish(path,root,now)
 return specific,health(root,now,attempts)

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--source');parser.add_argument('--output-dir',default='results')
 args=parser.parse_args();now=datetime.now(ET)
 if args.source:publish(args.source,Path(args.output_dir),now)
 _,report=refresh(Path(args.output_dir),now)
 print(json.dumps(report,sort_keys=True))
