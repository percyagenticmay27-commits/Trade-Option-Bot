"""One-shot end-of-session expiry sweep, Cboe close reconciliation and EOD report."""
import argparse,json,sys,os,subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from option_bot.session_expiration import _calendar
from option_bot.post_session import sweep_and_reconcile
from option_bot.local_paper import _atomic, _decimal

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output-dir',type=Path,default=ROOT/'results')
    ap.add_argument('--no-network',action='store_true',help='Reconcile only if verified Cboe history injected elsewhere; testing only')
    args=ap.parse_args()
    if args.no_network:raise SystemExit('NO_NETWORK_NOT_SUPPORTED_FOR_PRODUCTION')
    root=args.output_dir;now=datetime.now(ZoneInfo('America/New_York'))
    # The 13:02 ET early-close check must NOT run management during a
    # regular 16:00 ET session. Retry after the actual exchange close only.
    calendar=_calendar(now.year)
    today=now.date().isoformat()
    if calendar.is_session(today) and now<calendar.session_close(today).to_pydatetime().astimezone(ZoneInfo('America/New_York')):
        print(json.dumps({'status':'WAITING_FOR_EXCHANGE_CLOSE','as_of_et':now.isoformat(),
                          'paper_only':True,'broker_submissions':0}))
        return 0
    # First run regular manager with entries explicitly disabled; this manages
    # baseline and independently held shadow positions, and expires every due
    # leg through the exchange calendar. The baseline sweep below is a
    # separate fail-safe if that manager cannot access fresh option quotes.
    env=dict(os.environ,OPTION_BOT_TIMEZONE='America/New_York')
    env.pop('SHADOW_EARLY_ENTRY_SCAN',None)
    try:
        proc=subprocess.run([str(ROOT/'scripts/run_option_bot.sh'),'manage-once'],
            cwd=ROOT,env=env,timeout=75,capture_output=True,text=True,check=False)
        management={'exit_code':proc.returncode,'status':'MANAGED' if proc.returncode==0 else 'MANAGER_DEGRADED',
                    'last_output':(proc.stdout+'\n'+proc.stderr)[-350:]}
    except (OSError,subprocess.TimeoutExpired) as exc:
        management={'status':'MANAGER_UNAVAILABLE','reason':type(exc).__name__}
    report,state=sweep_and_reconcile(root/'option_001_paper_ledger.json',root/'barney_end_of_day.json',now)
    # Independent shadow books must not leave their 0DTE expirations open.
    # Their reconciliation, P/L, and alerts remain completely separate from
    # baseline OPTION-001 capital and performance.
    shadow_books={}
    for strategy,file in (
        ('EARLY_REVERSAL_EMA9_20_SHADOW','early_reversal_shadow_paper_ledger.json'),
        ('OPENING_RANGE_VWAP_REGIME_SHADOW_V1','opening_range_shadow_paper_ledger.json')):
        ledger=root/file
        if not ledger.exists():
            shadow_books[strategy]={'status':'NO_LEDGER','open_positions':0}
            continue
        eod_path=root/(file.replace('_paper_ledger.json','_barney_end_of_day.json'))
        sr,_=sweep_and_reconcile(ledger,eod_path,now)
        shadow_books[strategy]={k:sr[k] for k in (
            'status','open_positions','settlement_reconciled_total',
            'settlement_pending_count','cumulative_realized_pnl_usd')}
    report['strategy_books']={'OPTION_001_BASELINE':{
        'status':report['status'],'open_positions':report['open_positions'],
        'settlement_pending_count':report['settlement_pending_count'],
        'cumulative_realized_pnl_usd':report['cumulative_realized_pnl_usd']},**shadow_books}
    report['intraday_manager_post_close']=management
    report['unresolved_settlements_all_books']=sum(
        row.get('settlement_pending_count',0) for row in report['strategy_books'].values())
    if report['unresolved_settlements_all_books']:
        report['status']='SETTLEMENT_PENDING_ATTENTION'
    _atomic(root/'barney_end_of_day.json',report)
    # Keep existing public OPTION-001 report summaries in sync under their
    # own atomic writes; background bot scans may overwrite with newer state.
    for name in ('option_001_positions.json','option_001_summary.json'):
        p=root/name
        if not p.exists():continue
        current=json.loads(p.read_text())
        current.update(generated_at_utc=now.isoformat(),
            open=list(state['open']) if name=='option_001_positions.json' else current.get('open'),
            completed=list(state['completed']) if name=='option_001_positions.json' else current.get('completed'),
            settlement_pending_count=report['settlement_pending_count'],
            realized_pnl=report['cumulative_realized_pnl_usd'])
        if name=='option_001_summary.json':
            current.pop('open',None);current.pop('completed',None)
            current['open_count']=len(state['open']);current['completed_count']=len(state['completed'])
            if report['settlement_pending_count']:current['health']='DEGRADED'
        _atomic(p,current)
    print(json.dumps({k:report[k] for k in ('status','open_positions','expired_open_positions',
        'settlement_reconciled_total','settlement_pending_count','cumulative_realized_pnl_usd')},sort_keys=True))
    return 2 if report['unresolved_settlements_all_books'] else 0
if __name__=='__main__':raise SystemExit(main())
