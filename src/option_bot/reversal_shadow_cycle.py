"""Independent option paper ledger for early-reversal shadow at OPTION-001 timestamps.

Reuses the exact standard paper manager for fills/exits, but has its own state,
exposure and observations. This module cannot open broker orders or edit the
actual OPTION-001 ledger. Missing current options/underlying context => WAIT.
"""
from __future__ import annotations
import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Mapping
from option_bot.collection_policy import collection_plan
from option_bot.config import OptionBotConfig
from option_bot.domain import Decision
from option_bot.evidence import EvidenceEngine
from option_bot.live_scan import SetupEvaluator,indicators_for_bars
from option_bot.local_paper import LocalPaperSimulation,_atomic
from option_bot.market_context import alignment_context,project_structure_config
from option_bot.providers.base import Availability,EventGateEvidence
from option_bot.providers.robinhood_research import load_robinhood_research_bars,load_robinhood_research_surface
from option_bot.reversal_shadow import evaluate as reversal_evaluate
from option_bot.structures import StructureConfig,StructureGenerator
from option_bot.probability import MINIMUM_PROBABILITY_OF_PROFIT
from option_bot.intraday_clearance import clearance_levels

SYMBOLS=('SPX','XSP')

def run_cycle(config:OptionBotConfig,root:Path,now:datetime,*,allow_entries:bool,events:Mapping|None=None):
    """Call on every scheduled scan AND manage cycle; no independent timer."""
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    dedicated=root/'early_reversal_shadow_research.json'
    real_snapshot=dedicated if dedicated.exists() else root/'robinhood_option_research.json'
    # The simulator.path override below provides the book separation.
    shadow_config=config
    clock_date=now.date().isoformat()
    assessments=[]
    research={}
    try:research=json.loads(real_snapshot.read_text())
    except (OSError,ValueError):pass
    from option_bot.local_paper import _fresh
    fresh=(_fresh(research.get('generated_at_utc'),now) and
           research.get('research_only') is True and
           research.get('order_submission_enabled') is False and
           research.get('source')=='ROBINHOOD_MCP_RESEARCH')
    snapshots={}
    for symbol in SYMBOLS:
        item={'symbol':symbol,'at':now.isoformat(),'strategy':'EARLY_REVERSAL_EMA9_20_SHADOW',
              'status':'DATA_UNAVAILABLE','reason':'FRESH_PROVIDER_SNAPSHOT_REQUIRED',
              'paper_only':True,'broker_submissions':0}
        bars=load_robinhood_research_bars(real_snapshot,symbol)
        if bars and bars[-1].timestamp.date()==now.date():
            indicators=indicators_for_bars(bars)
            signal=reversal_evaluate(symbol,indicators,now)
            item.update(signal)
            snapshots[symbol]=(indicators,bars)
        else:
            item.update(status='DATA_UNAVAILABLE',reason='CURRENT_COMPLETED_5M_BARS_UNAVAILABLE')
        if not fresh and item['status']=='SIGNAL_OBSERVED':
            item.update(status='DATA_UNAVAILABLE',reason='FRESH_OPTION_SNAPSHOT_REQUIRED')
        assessments.append(item)
    qualified=[]
    model=EvidenceEngine.from_file(Path(__file__).resolve().parents[2]/'configs/evidence-model-v1.json')
    event_ok=((events or {}).get('trade_date')==clock_date and
              (events or {}).get('scheduled_calendar_status')=='AVAILABLE' and
              (events or {}).get('event_gate')=='CLEAR')
    event_rows={x.get('symbol'):x for x in (events or {}).get('symbols',[]) if isinstance(x,dict)}
    for item in assessments:
        symbol=item['symbol']
        if item.get('status')!='SIGNAL_OBSERVED' or not fresh:continue
        if not event_ok or event_rows.get(symbol,{}).get('earnings_gate') not in ('CLEAR',None):
            item.update(status='BLOCKED',reason='EVENT_GATE_NOT_VERIFIED');continue
        try:
            indicators,bars=snapshots[symbol]
            surface=load_robinhood_research_surface(real_snapshot,symbol,clock_date,now)
            if surface.availability is not Availability.AVAILABLE:
                item.update(status='DATA_UNAVAILABLE',reason='SHADOW_OPTION_CHAIN_NOT_COLLECTED',
                            quote_reasons=list(surface.reason_codes));continue
            raw_context=json.loads((surface.evidence or {})['market_context_json'])
            flags,audit=alignment_context(raw_context,now)
            if audit.get('status')!='AVAILABLE':raise ValueError('MARKET_ALIGNMENT_UNAVAILABLE')
            # Use actual bar evidence, not the EMA50 gate, to select direction.
            bias=item['direction']
            initial=StructureConfig(bias,min(indicators.opening_range_low,indicators.previous_low),
                max(indicators.opening_range_high,indicators.previous_high),
                indicators.price-D(str(indicators.atr14)),indicators.price+D(str(indicators.atr14)),
                config.loss_limit_for(symbol),landing_zone=indicators.price,
                directional_credit_only=True,call_debit_enabled=bias=='BULLISH')
            levels=clearance_levels(bars,now,bias)
            initial=replace(initial,support=levels['support'] if levels['support'] is not None else initial.support,
                resistance=levels['resistance'] if levels['resistance'] is not None else initial.resistance)
            projected,projection=project_structure_config(initial,symbol,surface.evidence['bar_source_symbol'],raw_context,now)
            event=EventGateEvidence(symbol,Availability.AVAILABLE,False,(),())
            evaluator=SetupEvaluator(score=model.score,generate=StructureGenerator.generate,
                trade_threshold=int(model.model['trade_threshold']),
                watch_threshold=int(model.model['watch_threshold']),
                max_loss=config.loss_limit_for(symbol),score_advisory=True)
            evaluated=evaluator.evaluate(symbol,indicators,surface,event,projected)
            item.update(direction=bias,structure_decision=evaluated.decision.value,
                        structure_reasons=list(evaluated.reason_codes),
                        candidate_id=evaluated.trade_candidate.candidate_id if evaluated.trade_candidate else None,
                        projection=projection,status='STRUCTURE_EVALUATED')
            if evaluated.decision is Decision.TRADE and evaluated.trade_candidate is not None:
                # Explicitly isolated paper candidate; main bot has no access.
                qualified.append(evaluated)
        except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
            item.update(status='DATA_UNAVAILABLE',reason='SHADOW_EVIDENCE_UNVERIFIED',detail=str(exc)[:160])
    # Reuse exactly the same paper opening/exit manager, but with independent
    # state, no broker order transport, and no effects on OPTION-001 ledger.
    simulator=LocalPaperSimulation(shadow_config)
    simulator.path=root/'early_reversal_shadow_paper_ledger.json'
    paper=simulator.cycle(qualified,real_snapshot,now,
       allow_entries=allow_entries and fresh and event_ok)
    for item in assessments:
        item['paper_fills_this_cycle']=sum(x.get('symbol')==item['symbol'] and x['action']=='PAPER_OPEN'
                     for x in paper['new_events'])
    # Comparable closed-paper-trade performance. Pending expiration outcomes
    # are not silently scored as wins and path drawdown is closed-trade-only.
    completed=sorted((p for p in paper['completed'] if p.get('realized_pnl') is not None),
                     key=lambda p:p.get('closed_at') or '')
    gains=[D(str(p['realized_pnl'])) for p in completed]
    running=peak=drawdown=D('0')
    for gain in gains:
        running+=gain;peak=max(peak,running);drawdown=max(drawdown,peak-running)
    performance={'closed_verified':len(gains),'wins':sum(x>0 for x in gains),
                 'losses':sum(x<0 for x in gains),
                 'win_rate_pct':str((D(sum(x>0 for x in gains))*100/len(gains)).quantize(D('.01'))) if gains else None,
                 'realized_pnl_usd':str(running.quantize(D('.01'))),
                 'closed_trade_sequence_max_drawdown_usd':str(drawdown.quantize(D('.01'))),
                 'unresolved_settlements':sum(p.get('settlement_status')=='PENDING' for p in paper['completed']),
                 'drawdown_scope':'CLOSED_TRADE_SEQUENCE_ONLY_NOT_INTRATRADE'}
    report={'generated_at_et':now.isoformat(),'trade_date':clock_date,
       'mode':'INDEPENDENT_SHADOW_PAPER_SIMULATION','paper_only':True,
       'broker_submissions':0,'entry_window':'SAME_AS_OPTION_001',
       'management_window':'EVERY_OPTION_001_MANAGEMENT_CYCLE',
       'results':assessments,'new_events':paper['new_events'],
       'open_count':len(paper['open']),'completed_count':len(paper['completed']),
       'realized_pnl':paper['realized_pnl'],'performance':performance,
       'execution_rejections':paper['execution_rejections'],
       'actual_option_positions_file':'option_001_paper_ledger.json',
       'shadow_option_positions_file':'early_reversal_shadow_paper_ledger.json',
       'quote_source_file':real_snapshot.name}
    _atomic(root/'option_001_early_reversal_shadow_latest.json',report)
    with (root/'option_001_early_reversal_shadow_observations.jsonl').open('a') as output:
        output.write(json.dumps(report,default=str)+'\n')
    return report
