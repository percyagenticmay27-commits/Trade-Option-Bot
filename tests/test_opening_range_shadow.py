from dataclasses import replace
from datetime import datetime,timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import json
import pytest
from option_bot.indicators import Bar
from option_bot.opening_range_shadow import evaluate
from option_bot.opening_range_shadow_cycle import run_cycle,generate_credit_structures
from option_bot.local_paper import FLAGS,_atomic
from test_reversal_shadow_cycle import configuration

ET=ZoneInfo('America/New_York')
NOW=datetime(2026,11,17,10,0,tzinfo=ET)
I=SimpleNamespace(available=True,atr14=2.,adx14=10.,chop14=65.,relative_volume=9.)

def bar(stamp,close='100',low='99',high='101',volume=100):
    return Bar(stamp,D('100'),D(high),D(low),D(close),volume)

def samples(kind='range',history=3):
    rows=[]
    for day in (12,13,16)[-history:] if history else []:
        for slot in range(6):
            rows.append(bar(datetime(2026,11,day,9,30,tzinfo=ET)+timedelta(minutes=5*slot)))
    start=NOW.replace(hour=9,minute=30)
    closes=['100.2','99.8','100.1','100.3','99.7','100.2']
    current=[bar(start+timedelta(minutes=5*n),c) for n,c in enumerate(closes)]
    if kind=='bull':
        current=current[:3]+[bar(start+timedelta(minutes=15),'101.5','100','102',200),
            bar(start+timedelta(minutes=20),'102.2','100','103',200)]
    if kind=='bear':
        current=current[:3]+[bar(start+timedelta(minutes=15),'98.5','98','100',200),
            bar(start+timedelta(minutes=20),'97.8','97','100',200)]
    return rows+current

def test_0845_only_fixes_range_no_entry():
    rows=samples()[:-3]
    out=evaluate('SPX',I,rows,NOW.replace(hour=9,minute=45))
    assert out['status']=='WAIT'
    assert out['evidence']['opening_range_low']=='99'
    assert out['evidence']['opening_range_high']=='101'

@pytest.mark.parametrize('kind,direction',[('bull','BULLISH'),('bear','BEARISH')])
def test_breakout_two_closes_overrides_lagging_chop(kind,direction):
    out=evaluate('SPX',I,samples(kind),NOW.replace(hour=9,minute=55))
    assert out['status']=='SIGNAL_OBSERVED'
    assert out['direction']==direction
    assert len(out['candidate_option_types'])==1

def test_range_requires_both_rejections_flat_vwap_and_crosses():
    out=evaluate('SPX',I,samples(),NOW)
    assert out['status']=='SIGNAL_OBSERVED'
    assert out['direction']=='NEUTRAL'
    assert out['evidence']['relative_volume_at_time']=='1'
    assert out['evidence']['inherited_relative_volume']=='9.0'
    assert out['evidence']['relative_volume_prior_sessions']==3

def test_volume_history_missing_is_not_zero_volume_or_permission():
    out=evaluate('XSP',I,samples(history=2),NOW)
    assert out['status']=='DATA_UNAVAILABLE'
    assert out['reason']=='TIME_MATCHED_RELATIVE_VOLUME_HISTORY_UNAVAILABLE'

def test_future_bar_cannot_establish_breakout():
    rows=samples('bull')
    out=evaluate('SPX',I,rows,NOW.replace(hour=9,minute=50))
    assert out['status']=='WAIT'
    assert out['evidence']['current_completed_bars']==4

def test_stale_bars_and_incomplete_grid_fail_closed():
    assert evaluate('SPX',I,samples(),NOW+timedelta(minutes=6))['reason']=='COMPLETED_BARS_STALE'
    rows=samples();del rows[-4]
    assert evaluate('SPX',I,rows,NOW)['reason']=='CURRENT_SESSION_GRID_INCOMPLETE'

def test_same_result_when_observation_time_is_central():
    a=evaluate('SPX',I,samples(),NOW)
    b=evaluate('SPX',I,samples(),NOW.astimezone(ZoneInfo('America/Chicago')))
    assert a['direction']==b['direction']=='NEUTRAL'

def test_low_volume_does_not_confirm_breakout():
    rows=samples('bull');rows[-1]=replace(rows[-1],volume=10);rows[-2]=replace(rows[-2],volume=10)
    assert evaluate('SPX',I,rows,NOW.replace(hour=9,minute=55))['reason']=='BREAKOUT_PARTICIPATION_NOT_CONFIRMED'

def test_recent_range_break_cannot_be_neutral():
    rows=samples();rows[-1]=bar(rows[-1].timestamp,'102','99','103')
    assert evaluate('SPX',I,rows,NOW)['reason']=='RECENT_OPENING_RANGE_BREAK_TRANSITION'

def test_new_book_missing_snapshot_preserves_other_two_books(tmp_path):
    old=dict(schema_version='1.0',**FLAGS,open=[],completed=[],events=[])
    paths=[tmp_path/'option_001_paper_ledger.json',tmp_path/'early_reversal_shadow_paper_ledger.json']
    for p in paths:_atomic(p,old)
    before=[p.read_bytes() for p in paths]
    r=run_cycle(configuration(tmp_path),tmp_path,NOW,allow_entries=True,events={})
    assert r['broker_submissions']==0 and not r['new_events']
    assert (tmp_path/'opening_range_shadow_paper_ledger.json').exists()
    assert [p.read_bytes() for p in paths]==before
    comparison=json.loads((tmp_path/'option_001_three_strategy_comparison.json').read_text())
    assert len(comparison['strategies'])==3
    assert comparison['strategies'][-1]['win_rate_pct'] is None

def test_dedicated_research_precedes_main_without_mutating_main(tmp_path):
    doc=dict(source='ROBINHOOD_MCP_RESEARCH',research_only=True,
             order_submission_enabled=False,generated_at_utc=NOW.isoformat(),symbols={})
    for name in ['robinhood_option_research.json','opening_range_shadow_research.json']:
        _atomic(tmp_path/name,doc)
    before=(tmp_path/'robinhood_option_research.json').read_bytes()
    r=run_cycle(configuration(tmp_path),tmp_path,NOW,allow_entries=False,events={})
    assert r['quote_source_file']=='opening_range_shadow_research.json'
    assert (tmp_path/'robinhood_option_research.json').read_bytes()==before

def test_condor_credit_floor_applies_without_changing_original_generator(monkeypatch):
    from option_bot.domain import StructureType
    from option_bot.structures import StructureGeneration,StructureAttempt,StructureGenerator
    from option_bot.payoff import PayoffProfile
    from option_bot.domain import Money
    candidate=SimpleNamespace(structure_type=StructureType.IRON_CONDOR,legs=(),net_credit=Money(D('.50')),
                              product=SimpleNamespace(multiplier=100))
    attempt=StructureAttempt(D('.1'),True,frozenset(),candidate)
    monkeypatch.setattr(StructureGenerator,'generate',lambda *a:StructureGeneration((attempt,)))
    monkeypatch.setattr(PayoffProfile,'evaluate',lambda *a:SimpleNamespace(maximum_loss=Money(D(450)),maximum_profit=Money(D(50))))
    result=generate_credit_structures(None,None,SimpleNamespace(bias='NEUTRAL',min_credit_profit_to_max_loss=D('.15')))
    assert not result.candidates
    assert 'PROFIT_TO_MAX_LOSS_BELOW_MINIMUM' in result.attempts[0].reason_codes
    assert attempt.accepted and attempt.candidate is candidate


from test_local_paper_runtime import runtime

@pytest.mark.parametrize('command,entry_flag,expected',[
    ('scan-once',False,True),('manage-once',False,False),
    ('manage-once',True,True),('close-all-paper',True,False)])
def test_cli_runs_both_shadows_with_correct_entry_permission(runtime,monkeypatch,command,entry_flag,expected):
    from option_bot import reversal_shadow_cycle,opening_range_shadow_cycle
    clock,setup,snapshot,run,report,root=runtime
    snapshot([])
    calls=[]
    monkeypatch.setattr(reversal_shadow_cycle,'run_cycle',lambda *a,**kw:calls.append(('early',kw['allow_entries'])))
    monkeypatch.setattr(opening_range_shadow_cycle,'run_cycle',lambda *a,**kw:calls.append(('opening',kw['allow_entries'])))
    if entry_flag:monkeypatch.setenv('SHADOW_EARLY_ENTRY_SCAN','1')
    else:monkeypatch.delenv('SHADOW_EARLY_ENTRY_SCAN',raising=False)
    assert run(command)==0
    assert ('opening',expected) in calls
    assert any(x[0]=='early' for x in calls)


def test_early_shadow_error_does_not_suppress_third(runtime,monkeypatch):
    from option_bot import reversal_shadow_cycle,opening_range_shadow_cycle
    clock,setup,snapshot,run,report,root=runtime
    snapshot([])
    def fail(*a,**kw):raise ValueError('test earlier shadow failure')
    calls=[]
    monkeypatch.setattr(reversal_shadow_cycle,'run_cycle',fail)
    monkeypatch.setattr(opening_range_shadow_cycle,'run_cycle',lambda *a,**kw:calls.append(kw['allow_entries']))
    assert run()==0
    assert calls==[True]
