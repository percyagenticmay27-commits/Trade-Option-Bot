"""Report trend-transition WAIT without mislabeling genuine bars as missing data."""
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse,json

TREND_WAIT='WAIT_FOR_TREND_CONFIRMATION'

def is_trend_wait(plan,now, max_age=60):
    try:
        if plan.get('source')!='ROBINHOOD_MCP_RESEARCH' or plan.get('order_submission_enabled') is not False:return False
        at=datetime.fromisoformat(plan['generated_at_et'].replace('Z','+00:00'))
        if at.tzinfo is None or not -5<=(now-at).total_seconds()<=max_age:return False
        main=[plan['symbols'][s] for s in ('SPX','XSP')]
        return all(row.get('status')==TREND_WAIT and row.get('reason')=='VWAP_EMA50_TREND_CONFLICT'
                   and row.get('candidate_option_types')==[] and row.get('last_completed_bar') for row in main)
    except (ValueError,KeyError,TypeError,AttributeError):return False

def main():
    p=argparse.ArgumentParser();p.add_argument('plan');p.add_argument('--output');args=p.parse_args()
    try:plan=json.loads(Path(args.plan).read_text())
    except (OSError,ValueError):return 1
    now=datetime.now(timezone.utc)
    if not is_trend_wait(plan,now):return 1
    result={'status':TREND_WAIT,'trade_date':now.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
            'observed_at_utc':now.isoformat(),'reason':'VWAP_EMA50_TREND_CONFLICT',
            'data_status':'FRESH_DIRECTION_EVIDENCE','option_lookup':'SKIPPED_CONSERVATIVELY',
            'scan_executed':False,'paper_entries':0,'paper_only':True,'broker_submissions':0,
            'symbols':{s:{'last_completed_bar':plan['symbols'][s]['last_completed_bar'],
                          'status':TREND_WAIT} for s in ('SPX','XSP')}}
    if args.output:
        from option_bot.local_paper import _atomic
        _atomic(Path(args.output),result)
    print(json.dumps(result,sort_keys=True))
    return 10

if __name__=='__main__':raise SystemExit(main())
