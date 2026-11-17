"""Side-by-side paper performance, never a combined capital account."""
import json
from decimal import Decimal as D
from option_bot.local_paper import _atomic

BOOKS=(('OPTION-001','option_001_paper_ledger.json'),
       ('EARLY_REVERSAL_EMA9_20_SHADOW','early_reversal_shadow_paper_ledger.json'),
       ('OPENING_RANGE_VWAP_REGIME_SHADOW_V1','opening_range_shadow_paper_ledger.json'))

def write_comparison(root,now):
    rows=[]
    for strategy,name in BOOKS:
        try:
            state=json.loads((root/name).read_text())
        except (OSError,ValueError):
            rows.append({'strategy':strategy,'status':'DATA_UNAVAILABLE','ledger':name})
            continue
        verified=sorted((p for p in state['completed'] if p.get('realized_pnl') is not None),key=lambda p:p.get('closed_at') or '')
        gains=[D(str(p['realized_pnl'])) for p in verified]
        total=peak=drawdown=D(0)
        for gain in gains:
            total+=gain;peak=max(peak,total);drawdown=max(drawdown,peak-total)
        today=[p for p in verified if str(p.get('closed_at',''))[:10]==now.date().isoformat()]
        rows.append({'strategy':strategy,'status':'AVAILABLE','ledger':name,
            'open_count':len(state['open']),'closed_verified':len(gains),
            'wins':sum(g>0 for g in gains),'losses':sum(g<0 for g in gains),
            'breakeven':sum(g==0 for g in gains),
            'win_rate_pct':str((D(sum(g>0 for g in gains))*100/len(gains)).quantize(D('.01'))) if gains else None,
            'realized_pnl_usd':str(total.quantize(D('.01'))),
            'today_realized_pnl_usd':str(sum((D(str(p['realized_pnl'])) for p in today),D(0)).quantize(D('.01'))),
            'unresolved_settlements':sum(p.get('realized_pnl') is None for p in state['completed']),
            'closed_trade_sequence_max_drawdown_usd':str(drawdown.quantize(D('.01')))})
    report={'generated_at_et':now.isoformat(),'paper_only':True,'broker_submissions':0,
            'scope':'INDEPENDENT_HYPOTHETICAL_BOOKS_NOT_COMBINED_CAPITAL',
            'comparison_caveat':'Different inception dates; compare matched forward sessions, not cumulative totals alone.',
            'pnl_basis':'SIMULATED_LEDGER_PRICES; NO_ADDITIONAL_FEES_OR_SLIPPAGE_DEDUCTED',
            'drawdown_scope':'CLOSED_TRADE_SEQUENCE_ONLY_NOT_INTRATRADE','strategies':rows}
    _atomic(root/'option_001_three_strategy_comparison.json',report)
    return report
