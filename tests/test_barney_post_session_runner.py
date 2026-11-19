"""End-to-end local runner uses independent paper books after real exchange close."""
import importlib.util
import json
import sys
from datetime import datetime,date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from option_bot.local_paper import FLAGS,_atomic
from option_bot import post_session

ET=ZoneInfo('America/New_York')

def _position(position_id):
 return {**FLAGS,'position_id':position_id,'symbol':'SPX',
  'premium_type':'CREDIT','entry_price':'0.45','quantity':1,'status':'OPEN',
  'realized_pnl':None,'product':{'settlement_type':'CASH','exercise_style':'EUROPEAN','multiplier':100},
  'legs':[{'right':right,'side':side,'strike':str(strike),'expiration':'2026-11-18','quantity':1}
   for right,side,strike in [('PUT','SELL',7230),('PUT','BUY',7225),('CALL','SELL',7435),('CALL','BUY',7440)]]}

def test_sweeps_baseline_and_each_shadow_without_sharing_pnl(tmp_path,monkeypatch):
 path=Path(__file__).resolve().parents[1]/'scripts/barney_post_session.py'
 spec=importlib.util.spec_from_file_location('test_runner_target',path)
 module=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(module)
 for name,pid in [('option_001_paper_ledger.json','A'),('early_reversal_shadow_paper_ledger.json','B'),('opening_range_shadow_paper_ledger.json','C')]:
  _atomic(tmp_path/name,{'schema_version':'1.0',**FLAGS,'open':[_position(pid)],'completed':[],'events':[]})
 class Clock:
  @staticmethod
  def now(tz=None):return datetime(2026,11,19,17,5,tzinfo=ET)
 monkeypatch.setattr(module,'datetime',Clock)
 monkeypatch.setattr(module.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout='NO_ORDERS',stderr=''))
 monkeypatch.setattr(post_session,'fetch_cboe_closing_history',lambda **kw:({date(2026,11,18):Decimal('7323.63')},{'source':'CBOE_PUBLISHED_SPX_DAILY_CLOSE'}))
 monkeypatch.setattr(sys,'argv',[str(path),'--output-dir',str(tmp_path)])
 assert module.main()==0
 eod=json.loads((tmp_path/'barney_end_of_day.json').read_text())
 assert eod['unresolved_settlements_all_books']==0
 assert len(eod['strategy_books'])==3
 for book in eod['strategy_books'].values():
  assert book['open_positions']==0 and book['cumulative_realized_pnl_usd']=='45.00'
 assert eod['broker_submissions']==0
 assert module.main()==0
 for name in ('option_001_paper_ledger.json','early_reversal_shadow_paper_ledger.json','opening_range_shadow_paper_ledger.json'):
  book=json.loads((tmp_path/name).read_text())
  assert [e['action'] for e in book['events']]==['PAPER_EXPIRE','PAPER_CASH_SETTLE']
