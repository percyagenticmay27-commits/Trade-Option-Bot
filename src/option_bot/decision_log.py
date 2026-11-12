"""Durable, immutable per-scan records and daily/weekly review indexes."""
from datetime import timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import json
from decimal import Decimal

def rule_checks(row):
    details=row.get("decision_details") or {}
    checks=[{"setting":"Technical score","required":row.get("technical_score_policy"),"observed":row.get("direction_score"),"status":"ADVISORY" if row.get("technical_score_policy")=="ADVISORY_DIRECTION_AND_RANKING" else "RECORDED"},
            {"setting":"Primary strategy/regime","required":"BULLISH put credit / BEARISH call credit / NEUTRAL condor","observed":details.get("bias"),"status":"RECORDED" if details.get("bias") else "DATA_UNAVAILABLE"}]
    band=(row.get("market_context") or {}).get("bollinger")
    if band:
        checks.append({"setting":"Bollinger condor boundaries","required":"20 completed 5-minute closes; shorts outside +/-2.2 population SD","observed":band,"status":"RECORDED"})
    for attempt in details.get("attempts",[]):
        v=attempt.get("observed") or {}
        for label,key,limit,op in [("Credit short delta","short_delta",".25","le"),("Credit return","profit_to_max_loss",".15","ge"),("Debit short delta","short_delta",".75","ge"),("Debit return","profit_to_cost",".20","ge"),("Structure probability proxy","probability_proxy",".75","ge")]:
            kind=v.get("structure","")
            if label.startswith("Credit") and "CREDIT_SPREAD" not in kind:continue
            if label.startswith("Debit") and "DEBIT_SPREAD" not in kind:continue
            actual=v.get(key)
            passed=None if actual is None else (Decimal(actual)<=Decimal(limit) if op=="le" else Decimal(actual)>=Decimal(limit))
            checks.append({"setting":label,"target_delta":attempt.get("target_delta"),"required":op+" "+limit,"observed":actual,"status":"DATA_UNAVAILABLE" if passed is None else "PASS" if passed else "FAIL"})
        checks.append({"setting":"Wings / structure attempt","target_delta":attempt.get("target_delta"),"observed":v or None,"status":"PASS" if attempt.get("accepted") else "FAIL" if v else "DATA_UNAVAILABLE","reasons":attempt.get("reason_codes",[])})
    # A high directional score does not override location/strike economics.
    # Report the specific observed structure geometry rather than leaving
    # TECHNICAL_CLEARANCE_REJECTED as a misleading generic score failure.
    settings=details.get("settings") or {}
    checks.append({"setting":"Directional score governs entry", "required":"ADVISORY only; location and payoff gates remain mandatory",
                   "observed":row.get("direction_score"), "status":"INFO" if row.get("technical_score_policy")=="ADVISORY_DIRECTION_AND_RANKING" else "SCORE_GATE_ACTIVE"})
    for attempt in details.get("attempts",[]):
        v=attempt.get("observed") or {}
        if "TECHNICAL_CLEARANCE_REJECTED" not in attempt.get("reason_codes",[]):continue
        kind=v.get("structure","")
        strike=v.get("short_strike")
        if strike is None:continue
        if kind=="PUT_CREDIT_SPREAD":
            barrier_names=("support","expected_lower")
            relation="short_put_strike < BOTH support and expected_lower"
        elif kind=="CALL_CREDIT_SPREAD":
            barrier_names=("resistance","expected_upper")
            relation="short_call_strike > BOTH resistance and expected_upper"
        else:continue
        observed={"structure":kind,"short_strike":strike,
                  **{n:settings.get(n) for n in barrier_names}}
        checks.append({"setting":"Strike vs technical barrier","required":relation,
                       "observed":observed,"status":"FAIL",
                       "target_delta":attempt.get("target_delta"),
                       "reasons":["TECHNICAL_CLEARANCE_REJECTED"]})
    return checks

def record_scan(output_dir, bundle, as_of, config, model):
    root=Path(output_dir)/"decision_history"
    day=bundle.summary["trade_date"]
    folder=root/day
    folder.mkdir(parents=True,exist_ok=True)
    run_id=as_of.strftime("%H%M%S%f")+"_"+uuid4().hex
    policy={**config,"technical_score_policy":model.get("technical_score_policy","MINIMUM_SCORE_GATE"),
            "candidate_collection_policy":model.get("candidate_collection_policy"),
            "bollinger_condor_policy":model.get("bollinger_condor_policy"),
            "directional_debit_enabled":model.get("candidate_collection_policy")=="DIRECTION_FIRST_CREDIT_PLUS_CALL_DEBIT_V2",
            "technical_trade_threshold":model.get("trade_threshold"),
            "technical_watch_threshold":model.get("watch_threshold"),
            "credit_short_delta_preferred":["0.15","0.20"],"credit_short_delta_ceiling":"0.25",
            "credit_min_profit_to_loss":"0.15","minimum_probability_proxy":"0.75",
            "debit_min_short_delta":"0.75","debit_min_profit_to_cost":"0.20"}
    positions=bundle.positions
    symbols=[{**row,"setting_checks":rule_checks(row)} for row in bundle.leaderboard]
    doc={"schema_version":"1.0","run_id":run_id,"trade_date":day,
         "ran_at_et":as_of.astimezone(ZoneInfo("America/New_York")).isoformat(),
         "ran_at_ct":as_of.astimezone(ZoneInfo("America/Chicago")).isoformat(),
         "policy":policy,"record_origin":model.get("record_origin","RUNTIME_SCAN"),"paper_only":True,"order_submission_enabled":False,
         "outcome":"NEW_PAPER_EVENTS" if positions.get("new_events") else "NO_NEW_PAPER_ENTRY",
         "symbols":symbols,"execution":positions,
         "notice":"Missing observed values remain null/unavailable; no inferred historical quotes."}
    for key, filename in [("event_evidence","option_001_scan_events.json"),("collection_audit","option_001_scan_priority_audit.json"),("collection_plan","option_001_collection_plan.json")]:
        source=Path(output_dir)/filename
        doc[key]=json.loads(source.read_text()) if source.exists() else None
    name=folder/(run_id+".json")
    with name.open("x") as f:json.dump(doc,f,indent=2,default=str)
    lines=["# Decision history — "+day,"","All times shown in America/Chicago. Technical scores may be advisory; see each run's policy.","",
           "| Time CT | Symbol | Decision | Technical score | Reasons | Record |",
           "| --- | --- | --- | --- | --- | --- |"]
    decision_docs=[]
    for p in sorted(folder.glob("*.json")):
        d=json.loads(p.read_text())
        if not isinstance(d,dict) or not d.get("run_id") or not isinstance(d.get("symbols"),list):
            continue
        decision_docs.append((p,d))
        for row in d["symbols"]:
            reason=", ".join(row.get("reason_codes",[])) or row.get("reason","Qualified; see execution outcome")
            vals=[d["ran_at_ct"],row["symbol"],row["decision"],str(row.get("direction_score")),
                  reason,"["+p.stem+"]("+p.name+")"]
            lines.append("| "+" | ".join(v.replace("|","/") for v in vals)+" |")
    for saved,saved_doc in decision_docs:
      for row in saved_doc["symbols"]:
        lines.extend(["", "## "+row["symbol"]+" — "+saved_doc["ran_at_ct"], "",
                      "| Setting | Required | Observed | Status |", "| --- | --- | --- | --- |"])
        for check in row.get("setting_checks",[]):
            lines.append("| "+" | ".join(str(check.get(k,"")).replace("|","/") for k in ["setting","required","observed","status"])+" |")
    (folder/"README.md").write_text("\n".join(lines)+"\n")
    monday=as_of.astimezone(ZoneInfo("America/New_York")).date()
    monday-=timedelta(days=monday.weekday())
    weekly=["# Weekly decision history — "+str(monday),"","Open a daily index for observed values, rules and execution reasons.",""]
    for i in range(7):
        date=str(monday+timedelta(days=i))
        if (root/date/"README.md").exists():
            weekly.append("- ["+date+"]("+date+"/README.md)")
    (root/("week_"+str(monday)+".md")).write_text("\n".join(weekly)+"\n")
    bundle.summary["decision_history"]={"latest_record":"decision_history/"+day+"/"+name.name,
        "daily_index":"decision_history/"+day+"/README.md","weekly_index":"decision_history/week_"+str(monday)+".md"}
    return doc
