import copy
import json
from datetime import timedelta
import pytest
from option_bot.ema_shadow_research import publish,refresh,NAME
from option_bot.shadow_variant_cycle import run_cycle
from option_bot.shadow_variant_signals import EMA_TREND
from test_shadow_variant_models import ema_fixture
from test_reversal_shadow_cycle import configuration

def document(now,rows):
 bars=[dict(timestamp=b.timestamp.isoformat(),open=str(b.open),high=str(b.high),low=str(b.low),close=str(b.close),volume=b.volume) for b in rows]
 return dict(source='ROBINHOOD_MCP_RESEARCH',research_only=True,order_submission_enabled=False,
  generated_at_utc=now.isoformat(),symbols={s:dict(bar_source_symbol='SPY',bars=bars,contracts=[]) for s in ('SPX','XSP')})

def test_active_cycle_handoff_publishes_dedicated_feed_without_baseline_mutation(tmp_path,monkeypatch):
 rows,now=ema_fixture();doc=document(now,rows)
 source=tmp_path/'active_retry.json';source.write_text(json.dumps(doc))
 baseline=tmp_path/'robinhood_option_research.json';baseline.write_text('{"symbols":{}}')
 original=baseline.read_bytes();monkeypatch.setenv('ROBINHOOD_RESEARCH_SNAPSHOT_PATH',str(source))
 r=run_cycle(configuration(tmp_path),tmp_path,now,strategy=EMA_TREND,allow_entries=True,events={})
 assert r['quote_source_file']==NAME
 assert all(x['reason']=='EVENT_GATE_NOT_VERIFIED' for x in r['results']),r
 assert all(x['evidence']['bars_used']>=450 for x in r['results'])
 assert not r['new_events']
 assert baseline.read_bytes()==original
 saved=json.loads((tmp_path/NAME).read_text())
 assert saved['generated_at_utc']==doc['generated_at_utc']
 assert saved['symbols']==doc['symbols']
 assert r['research_feed_health']['status']=='REFRESH_REQUIRED' # No option quotes fabricated.

def test_stale_handoff_cannot_overwrite_newer_dedicated_data(tmp_path,monkeypatch):
 rows,now=ema_fixture();doc=document(now,rows)
 good=tmp_path/'good.json';good.write_text(json.dumps(doc));publish(good,tmp_path,now)
 before=(tmp_path/NAME).read_bytes()
 stale=tmp_path/'stale.json';doc['generated_at_utc']=(now-timedelta(days=1)).isoformat();stale.write_text(json.dumps(doc))
 monkeypatch.setenv('ROBINHOOD_RESEARCH_SNAPSHOT_PATH',str(stale))
 path,h=refresh(tmp_path,now)
 assert path==tmp_path/NAME and path.read_bytes()==before
 assert any(x.get('reason')=='SOURCE_SNAPSHOT_STALE' for x in h['input_attempts'])

def test_management_only_zero_bar_snapshot_cannot_replace_signal_history(tmp_path,monkeypatch):
 rows,now=ema_fixture();doc=document(now,rows)
 good=tmp_path/'good.json';good.write_text(json.dumps(doc));publish(good,tmp_path,now)
 before=(tmp_path/NAME).read_bytes()
 for s in doc['symbols']:doc['symbols'][s]['bars']=[]
 source=tmp_path/'management.json';source.write_text(json.dumps(doc))
 monkeypatch.setenv('ROBINHOOD_RESEARCH_SNAPSHOT_PATH',str(source));refresh(tmp_path,now)
 assert (tmp_path/NAME).read_bytes()==before

@pytest.mark.parametrize('problem',['short_history','wrong_proxy','live','bad_ohlc','duplicate'])
def test_invalid_provider_input_rejected_without_publication(tmp_path,problem):
 rows,now=ema_fixture();doc=document(now,rows)
 if problem=='short_history':
  for s in doc['symbols']:doc['symbols'][s]['bars']=doc['symbols'][s]['bars'][-10:]
 if problem=='wrong_proxy':doc['symbols']['SPX']['bar_source_symbol']='QQQ'
 if problem=='live':doc['order_submission_enabled']=True
 if problem=='bad_ohlc':doc['symbols']['SPX']['bars'][-1]['low']='9999'
 if problem=='duplicate':doc['symbols']['SPX']['bars'].append(doc['symbols']['SPX']['bars'][-1])
 source=tmp_path/'invalid.json';source.write_text(json.dumps(doc))
 with pytest.raises(ValueError):publish(source,tmp_path,now)
 assert not (tmp_path/NAME).exists()

def test_current_envelope_never_hides_stale_bars(tmp_path,monkeypatch):
 rows,then=ema_fixture();now=then+timedelta(minutes=20);doc=document(now,rows)
 source=tmp_path/'source.json';source.write_text(json.dumps(doc));publish(source,tmp_path,now)
 _,h=refresh(tmp_path,now)
 assert 'COMPLETED_BARS_STALE' in h['reasons']
 assert json.loads((tmp_path/NAME).read_text())['symbols']['SPX']['bars'][-1]['timestamp']==rows[-1].timestamp.isoformat()
