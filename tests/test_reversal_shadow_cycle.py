import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from option_bot.config import OptionBotConfig
from option_bot.reversal_shadow_cycle import run_cycle
from option_bot.local_paper import _atomic

ET=ZoneInfo('America/New_York')
NOW=datetime(2026,11,12,11,20,tzinfo=ET)

def configuration(tmp_path):
 from types import SimpleNamespace
 from datetime import time
 from decimal import Decimal as D
 return SimpleNamespace(database_path=tmp_path/'option_bot.sqlite3',paper_only=True,
  order_submission_enabled=False,max_daily_entries=2,max_daily_defined_loss=D('500'),
  entry_start=time(9,45),entry_end=time(12,0),mandatory_exit=time(15,30),
  loss_limit_for=lambda symbol:D('500') if symbol=='SPX' else D('100'))

def test_missing_snapshot_writes_separate_shadow_ledger_and_no_trades(tmp_path):
 result=run_cycle(configuration(tmp_path),tmp_path,NOW,allow_entries=True,events={})
 assert result['open_count']==0 and not result['new_events']
 assert result['broker_submissions']==0
 assert (tmp_path/'early_reversal_shadow_paper_ledger.json').exists()
 assert not (tmp_path/'option_001_paper_ledger.json').exists()
 assert all(row['status']=='DATA_UNAVAILABLE' for row in result['results'])
 assert result['quote_source_file']=='robinhood_option_research.json'

def test_dedicated_shadow_quote_source_takes_precedence(tmp_path):
 from option_bot.local_paper import FLAGS
 _atomic(tmp_path/'robinhood_option_research.json',dict(FLAGS,source='ROBINHOOD_MCP_RESEARCH',
  research_only=True,order_submission_enabled=False,generated_at_utc=NOW.isoformat(),symbols={}))
 _atomic(tmp_path/'early_reversal_shadow_research.json',dict(FLAGS,source='ROBINHOOD_MCP_RESEARCH',
  research_only=True,order_submission_enabled=False,generated_at_utc=NOW.isoformat(),symbols={}))
 r=run_cycle(configuration(tmp_path),tmp_path,NOW,allow_entries=True,events={})
 assert r['quote_source_file']=='early_reversal_shadow_research.json'
 assert not (tmp_path/'option_001_paper_ledger.json').exists()

def test_management_with_no_quotes_never_generates_fake_exit(tmp_path):
 cfg=configuration(tmp_path)
 r=run_cycle(cfg,tmp_path,NOW,allow_entries=False,events={})
 assert r['open_count']==0 and r['completed_count']==0
 assert not r['new_events']

def test_shadow_performance_not_fabricated_without_verified_close(tmp_path):
 r=run_cycle(configuration(tmp_path),tmp_path,NOW,allow_entries=True,events={})
 assert r['performance']['closed_verified']==0
 assert r['performance']['win_rate_pct'] is None
 assert r['performance']['realized_pnl_usd']=='0.00'
 assert r['performance']['unresolved_settlements']==0
