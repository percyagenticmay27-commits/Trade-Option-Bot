from datetime import datetime
from zoneinfo import ZoneInfo
import json
from option_bot.decision_log import record_scan
from option_bot.reporting import ReportBundle
from test_high_delta_debits import generate

def test_rejected_debit_keeps_actual_values():
    result=generate("BULLISH",debit="4.50")
    rows=[a for a in result.attempts if "DEBIT_PROFIT_TO_COST_BELOW_MINIMUM" in a.reason_codes]
    assert rows[0].observed["net_debit"]=="4.50"
    assert rows[0].observed["maximum_loss"]=="450.00"
    assert rows[0].observed["short_delta"]=="0.80"
    assert float(rows[0].observed["profit_to_cost"]) < .20

def test_each_scan_is_preserved_with_policy_values_and_review_section(tmp_path):
    bundle=ReportBundle({"trade_date":"2026-10-23"},[
        {"symbol":"SPX","decision":"WATCH","reason_codes":["DEBIT_PROFIT_TO_COST_BELOW_MINIMUM"],
         "direction_score":60,"range_score":0,"technical_score_policy":"ADVISORY_DIRECTION_AND_RANKING",
         "decision_details":{"bias":"BULLISH","attempts":[{"observed":{"net_debit":"4.50"},"reason_codes":["DEBIT_PROFIT_TO_COST_BELOW_MINIMUM"]}]}}
    ],{"new_events":[],"daily_entry_count":0,"daily_defined_loss":"0.00"}, {})
    now=datetime(2026,10,23,11,0,tzinfo=ZoneInfo("America/New_York"))
    config={"max_daily_entries":2,"max_daily_defined_loss":"500.00"}
    record_scan(tmp_path,bundle,now,config,{"technical_score_policy":"ADVISORY_DIRECTION_AND_RANKING"})
    record_scan(tmp_path,bundle,now,config,{"technical_score_policy":"ADVISORY_DIRECTION_AND_RANKING"})
    runs=list((tmp_path/"decision_history/2026-10-23").glob("*.json"))
    assert len(runs)==2
    row=json.loads(runs[0].read_text())
    assert row["ran_at_ct"].startswith("2026-10-23T10:00")
    assert row["policy"]["technical_score_policy"]=="ADVISORY_DIRECTION_AND_RANKING"
    assert row["outcome"]=="NO_NEW_PAPER_ENTRY"
    assert row["symbols"][0]["decision_details"]["attempts"][0]["observed"]["net_debit"]=="4.50"
    assert "Decision history" in (tmp_path/"decision_history/2026-10-23/README.md").read_text()
    assert "2026-10-23" in (tmp_path/"decision_history/week_2026-10-19.md").read_text()

def test_high_advisory_score_still_explains_real_strike_clearance_and_premium():
    from option_bot.decision_log import rule_checks
    row={"technical_score_policy":"ADVISORY_DIRECTION_AND_RANKING", "direction_score":80,
      "decision_details":{"settings":{"support":"7590","expected_lower":"7580"},
        "attempts":[{"target_delta":"0.20", "accepted":False,
         "reason_codes":["TECHNICAL_CLEARANCE_REJECTED","PROFIT_TO_MAX_LOSS_BELOW_MINIMUM"],
         "observed":{"structure":"PUT_CREDIT_SPREAD","short_strike":"7600",
           "short_delta":"0.20","profit_to_max_loss":"0.11","maximum_loss":"450"}}]}}
    checks=rule_checks(row)
    assert any(c['setting']=='Directional score governs entry' and c['status']=='INFO' for c in checks)
    assert any(c['setting']=='Strike vs technical barrier' and c['status']=='FAIL'
       and c['observed']['short_strike']=='7600' and c['observed']['support']=='7590' for c in checks)
    assert any(c['setting']=='Credit return' and c['status']=='FAIL' and c['observed']=='0.11' for c in checks)
