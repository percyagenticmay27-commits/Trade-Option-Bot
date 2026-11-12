"""Determine permitted candidate option sides from actual bars before lookup."""
import argparse
import json
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from option_bot.live_scan import _bars,indicators_for_bars
from option_bot.collection_policy import collection_plan
from option_bot.reversal_shadow import evaluate as evaluate_reversal
from option_bot.local_paper import _atomic

def main():
    p=argparse.ArgumentParser()
    p.add_argument("current_bars",help="Actual Robinhood historicals response data or JSON with historicals list")
    p.add_argument("--history",help="Today's verified cached JSON with historicals list")
    p.add_argument("--symbols",nargs="+",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    as_of=datetime.now(ZoneInfo("America/New_York"))
    def rows(path):
        if not path:return []
        d=json.loads(Path(path).read_text())
        return d.get("historicals",d.get("data",d).get("results",[]))
    history=rows(args.history);current=rows(args.current_bars)
    plans={}
    shadow={}
    for symbol in args.symbols:
        proxy={"SPX":"SPY","XSP":"SPY","DJX":"DIA","MRUT":"IWM"}.get(symbol,symbol)
        merged={b["begins_at"]:b for r in history+current if r["symbol"]==proxy for b in r["bars"]}
        values=[]
        for _,b in sorted(merged.items()):
            stamp=datetime.fromisoformat(b["begins_at"].replace("Z","+00:00"))
            if stamp+timedelta(minutes=5)>as_of:continue
            values.append({**b,"timestamp":b["begins_at"],"open":b["open_price"],
                           "high":b["high_price"],"low":b["low_price"],"close":b["close_price"]})
        bars=_bars({"bars":values})
        fresh=bool(bars and bars[-1].timestamp.date()==as_of.date()
                   and as_of-bars[-1].timestamp<=timedelta(minutes=10))
        indicators=indicators_for_bars(bars) if fresh else None
        if symbol in {"SPX","XSP"}:
            if indicators is not None:
                shadow[symbol]=evaluate_reversal(symbol,indicators,as_of)
            else:
                shadow[symbol]={"strategy":"EARLY_REVERSAL_EMA9_20_SHADOW",
                    "status":"DATA_UNAVAILABLE","reason":"CURRENT_COMPLETED_BARS_UNAVAILABLE",
                    "paper_only":True,"paper_entries":0,"broker_submissions":0}
        plan=collection_plan(indicators) if fresh else {
            "status":"DATA_UNAVAILABLE","bias":None,"candidate_option_types":[],
            "reason":"CURRENT_COMPLETED_BARS_UNAVAILABLE","directional_debit_enabled":False}
        if plan["status"]=="AVAILABLE":
            from option_bot.intraday_clearance import clearance_levels
            try:
                plan["intraday_clearance"]=clearance_levels(bars,as_of,plan["bias"])
            except ValueError as exc:
                plan.update(status="DATA_UNAVAILABLE",candidate_option_types=[],reason=str(exc))
        if plan["status"]=="AVAILABLE" and plan["bias"]=="NEUTRAL" and symbol in {"SPX","XSP"}:
            from option_bot.bollinger import condor_bands
            try:
                plan["bollinger"]=condor_bands(bars,as_of)
                plan["bollinger"]["source_symbol"]=proxy
                plan["bollinger"]["projection_required"]=True
            except ValueError as exc:
                plan.update(status="DATA_UNAVAILABLE",candidate_option_types=[],reason=str(exc))
        plans[symbol]={**plan,"bar_source_symbol":proxy,"last_completed_bar":bars[-1].timestamp.isoformat() if bars else None}
    result={"source":"ROBINHOOD_MCP_RESEARCH","research_only":True,"order_submission_enabled":False,
            "generated_at_et":as_of.isoformat(),"policy":"DIRECTION_FIRST_CREDIT_PLUS_CALL_DEBIT_V2","symbols":plans}
    _atomic(Path(args.output),json.loads(json.dumps(result,default=str)))
    # Separate audit; existing option snapshot and entry gates are unchanged.
    _atomic(Path(args.output).with_name('option_001_early_reversal_shadow.json'),
            {'generated_at_et':as_of.isoformat(),'mode':'SHADOW_OBSERVATION_ONLY',
             'results':shadow,'paper_entries':0,'broker_submissions':0})
    print(json.dumps({s:{"status":v["status"],"bias":v["bias"],"candidate_option_types":v["candidate_option_types"]} for s,v in plans.items()}))
    # A complete, non-stale price observation with contradictory VWAP/EMA50
    # is a trading WAIT, not a provider refresh failure. Other missing
    # evidence remains error exit 2 and requests data recovery.
    statuses=[v["status"] for v in plans.values()]
    return 0 if all(v in {"AVAILABLE","WAIT_FOR_TREND_CONFIRMATION"} for v in statuses) else 2

if __name__=="__main__":
    raise SystemExit(main())
