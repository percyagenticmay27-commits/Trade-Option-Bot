"""Isolated paper-only runners for breakout-retest and EMA250/450 shadows.

Read-only research evidence, standalone paper ledgers, standard same-cycle
position management. No impact on original baseline or existing shadow books.
"""
from __future__ import annotations
import json
from dataclasses import replace
from datetime import datetime,timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Mapping
from option_bot.evidence import EvidenceEngine
from option_bot.domain import Decision
from option_bot.live_scan import SetupEvaluator,indicators_for_bars
from option_bot.local_paper import LocalPaperSimulation,_atomic,_fresh
from option_bot.market_context import alignment_context,project_structure_config
from option_bot.providers.base import Availability,EventGateEvidence
from option_bot.providers.robinhood_research import load_robinhood_research_bars,load_robinhood_research_surface
from option_bot.opening_range_shadow_cycle import generate_credit_structures
from option_bot.structures import StructureConfig
from option_bot.intraday_clearance import clearance_levels
from option_bot.shadow_variant_signals import RETEST,EMA_TREND,opening_retest,ema_250_450

VARIANTS={
 RETEST:('opening_range_retest_shadow',opening_retest),
 EMA_TREND:('ema250_450_shadow',ema_250_450),
}

def run_cycle(config,root:Path,now:datetime,*,strategy:str,allow_entries:bool,events:Mapping|None=None,
              force_close:bool=False,force_expiry_holds:bool=False):
 if strategy not in VARIANTS:raise ValueError('UNKNOWN_SHADOW_VARIANT')
 prefix,signal_fn=VARIANTS[strategy]
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 specific=root/(prefix+'_research.json')
 feed_health=None
 if strategy==EMA_TREND:
  from option_bot.ema_shadow_research import refresh
  snapshot,feed_health=refresh(root,now)
 else:
  snapshot=specific if specific.exists() else root/'robinhood_option_research.json'
 try:research=json.loads(snapshot.read_text())
 except (OSError,ValueError):research={}
 fresh=(_fresh(research.get('generated_at_utc'),now) and research.get('research_only') is True
        and research.get('source')=='ROBINHOOD_MCP_RESEARCH'
        and research.get('order_submission_enabled') is False)
 assessments=[];bars_by_symbol={}
 for symbol in ('SPX','XSP'):
  item={'strategy':strategy,'symbol':symbol,'at':now.isoformat(),
        'status':'DATA_UNAVAILABLE','reason':'FRESH_PROVIDER_SNAPSHOT_REQUIRED',
        'paper_only':True,'broker_submissions':0}
  bars=tuple(b for b in load_robinhood_research_bars(snapshot,symbol)
             if b.timestamp+timedelta(minutes=5)<=now)
  # Management cycles retain leg-manager responsibility without demanding
  # fresh EMA/ORB entry bars; an entry still fails closed on stale bars.
  if not allow_entries or force_close:
   item.update(status='MANAGEMENT_ONLY',reason='ENTRY_TECHNICALS_NOT_EVALUATED_MANAGEMENT_ONLY',
               most_recent_completed_bar_at=bars[-1].timestamp.isoformat() if bars else None)
  else:
   indicators=indicators_for_bars(bars)
   item.update(signal_fn(symbol,indicators,bars,now))
   if item.get('status')=='SIGNAL_OBSERVED' and not fresh:
    item.update(status='DATA_UNAVAILABLE',reason='FRESH_OPTION_SNAPSHOT_REQUIRED')
   bars_by_symbol[symbol]=(bars,indicators)
  assessments.append(item)
 model=EvidenceEngine.from_file(Path(__file__).resolve().parents[2]/'configs/evidence-model-v1.json')
 clock_date=now.date().isoformat()
 event_ok=((events or {}).get('trade_date')==clock_date and
   (events or {}).get('scheduled_calendar_status')=='AVAILABLE' and
   (events or {}).get('event_gate')=='CLEAR')
 event_rows={x.get('symbol'):x for x in (events or {}).get('symbols',[]) if isinstance(x,dict)}
 qualified=[]
 for item in assessments:
  symbol=item['symbol']
  if item.get('status')!='SIGNAL_OBSERVED' or not fresh:continue
  if not event_ok or event_rows.get(symbol,{}).get('earnings_gate') not in ('CLEAR',None):
   item.update(status='BLOCKED',reason='EVENT_GATE_NOT_VERIFIED');continue
  try:
   bars,indicators=bars_by_symbol[symbol]
   surface=load_robinhood_research_surface(snapshot,symbol,clock_date,now)
   if surface.availability is not Availability.AVAILABLE:
    item.update(status='DATA_UNAVAILABLE',reason='SHADOW_OPTION_CHAIN_NOT_COLLECTED',
                quote_reasons=list(surface.reason_codes));continue
   raw=json.loads((surface.evidence or {})['market_context_json'])
   _,audit=alignment_context(raw,now)
   if audit.get('status')!='AVAILABLE':raise ValueError('MARKET_ALIGNMENT_UNAVAILABLE')
   bias=item['direction']
   initial=StructureConfig(bias,min(indicators.opening_range_low,indicators.previous_low),
     max(indicators.opening_range_high,indicators.previous_high),
     indicators.price-D(str(indicators.atr14)),indicators.price+D(str(indicators.atr14)),
     config.loss_limit_for(symbol),landing_zone=indicators.price,
     directional_credit_only=True,call_debit_enabled=False)
   levels=clearance_levels(bars,now,bias)
   initial=replace(initial,
       support=levels['support'] if levels['support'] is not None else initial.support,
       resistance=levels['resistance'] if levels['resistance'] is not None else initial.resistance)
   projected,projection=project_structure_config(initial,symbol,surface.evidence['bar_source_symbol'],raw,now)
   evaluator=SetupEvaluator(score=model.score,generate=generate_credit_structures,
       trade_threshold=int(model.model['trade_threshold']),
       watch_threshold=int(model.model['watch_threshold']),
       max_loss=config.loss_limit_for(symbol),score_advisory=True)
   evaluated=evaluator.evaluate(symbol,indicators,surface,
     EventGateEvidence(symbol,Availability.AVAILABLE,False,(),()),projected)
   item.update(structure_decision=evaluated.decision.value,
     structure_reasons=list(evaluated.reason_codes),
     candidate_id=evaluated.trade_candidate.candidate_id if evaluated.trade_candidate else None,
     projection=projection,status='STRUCTURE_EVALUATED')
   if evaluated.decision is Decision.TRADE and evaluated.trade_candidate is not None:
    qualified.append(evaluated)
  except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
   item.update(status='DATA_UNAVAILABLE',reason='SHADOW_EVIDENCE_UNVERIFIED',detail=str(exc)[:160])
 manager=LocalPaperSimulation(config)
 manager.path=root/(prefix+'_paper_ledger.json')
 paper=manager.cycle(qualified,snapshot,now,
   allow_entries=allow_entries and fresh and event_ok and not force_close,
   force_close=force_close,force_expiry_holds=force_expiry_holds)
 for item in assessments:
  item['paper_fills_this_cycle']=sum(x.get('action')=='PAPER_OPEN' and x.get('symbol')==item['symbol'] for x in paper['new_events'])
 completed=sorted((p for p in paper['completed'] if p.get('realized_pnl') is not None),key=lambda p:p.get('closed_at') or '')
 gains=[D(str(x['realized_pnl'])) for x in completed]
 cumulative=peak=drawdown=D(0)
 for gain in gains:
  cumulative+=gain;peak=max(peak,cumulative);drawdown=max(drawdown,peak-cumulative)
 performance={'closed_verified':len(gains),'wins':sum(g>0 for g in gains),
  'losses':sum(g<0 for g in gains),
  'win_rate_pct':str((D(100)*sum(g>0 for g in gains)/len(gains)).quantize(D('.01'))) if gains else None,
  'realized_pnl_usd':str(cumulative.quantize(D('.01'))),
  'closed_trade_sequence_max_drawdown_usd':str(drawdown.quantize(D('.01'))),
  'unresolved_settlements':sum(p.get('realized_pnl') is None for p in paper['completed']),
  'drawdown_scope':'CLOSED_TRADE_SEQUENCE_ONLY_NOT_INTRATRADE'}
 report={'strategy':strategy,'generated_at_et':now.isoformat(),'trade_date':clock_date,
   'mode':'INDEPENDENT_SHADOW_PAPER_SIMULATION','paper_only':True,'broker_submissions':0,
   'entry_window':'SAME_AS_OPTION_001','management_window':'EVERY_OPTION_001_MANAGEMENT_CYCLE',
   'results':assessments,'new_events':paper['new_events'],
   'open_count':len(paper['open']),'completed_count':len(paper['completed']),
   'realized_pnl':paper['realized_pnl'],'performance':performance,
   'execution_rejections':paper['execution_rejections'],
   'actual_option_positions_file':'option_001_paper_ledger.json',
   'shadow_option_positions_file':prefix+'_paper_ledger.json',
   'quote_source_file':snapshot.name}
 if feed_health is not None:report['research_feed_health']=feed_health
 _atomic(root/(prefix+'_latest.json'),report)
 with (root/(prefix+'_observations.jsonl')).open('a') as out:out.write(json.dumps(report,default=str)+'\n')
 return report
