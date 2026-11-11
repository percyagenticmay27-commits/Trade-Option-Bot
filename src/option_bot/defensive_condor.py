"""Experimental *paper-only* opposite-side credit defense for held 0DTE verticals.

Never calls a broker or changes existing stop authority. Requires a complete
independently timestamped option surface already present in the snapshot.
"""
from __future__ import annotations
from datetime import time
from decimal import Decimal
from option_bot.domain import OptionLeg,OptionRight,TradeSide
from option_bot.payoff import PayoffProfile

START=time(10,0)      # CT; only after first OPTION-001 entry run
CUTOFF=time(12,30)   # CT; management/adjustments only
MIN_TRIGGER_FRACTION=Decimal('.20')
MAX_TRIGGER_FRACTION=Decimal('.50')
MIN_PREMIUM=Decimal('.10')
MAX_SHORT_DELTA=Decimal('.20')

def candidates(position,document,now,quote_legs,make_candidate,max_risk):
    """Return best verified improvement, or None; never mutate position."""
    from zoneinfo import ZoneInfo
    from option_bot.local_paper import _decimal
    ct=now.astimezone(ZoneInfo('America/Chicago'))
    if not (START<=ct.time().replace(tzinfo=None)<CUTOFF):return None
    if position.get('defensive_adjustment') or position.get('premium_type')!='CREDIT':return None
    if position.get('structure') not in {'CALL_CREDIT_SPREAD','PUT_CREDIT_SPREAD'}:return None
    if position.get('trade_date')!=ct.date().isoformat():return None
    if position.get('current_price') is None:return None
    original_risk=_decimal(position['maximum_loss'])
    opening=_decimal(position['entry_price'])
    current_loss=(_decimal(position['current_price'])-opening)*_decimal(position['product']['multiplier'])
    if not (original_risk*MIN_TRIGGER_FRACTION<=current_loss<original_risk*MAX_TRIGGER_FRACTION):return None
    legs=position['legs']
    if len(legs)!=2 or {x['right'] for x in legs}!={('CALL' if position['structure']=='CALL_CREDIT_SPREAD' else 'PUT')}:return None
    if len({x['expiration'] for x in legs})!=1:return None
    width=abs(_decimal(legs[0]['strike'])-_decimal(legs[1]['strike']))
    if width<=0:return None
    right='PUT' if position['structure']=='CALL_CREDIT_SPREAD' else 'CALL'
    short_opp=OptionRight.PUT if right=='PUT' else OptionRight.CALL
    rows=document.get('symbols',{}).get(position['symbol'],{}).get('contracts',[])
    original_strikes=[_decimal(x['strike']) for x in legs]
    available={}
    for r in rows:
        if (r.get('type','').upper()!=right or r.get('expiration_date')!=position['trade_date']
            or r.get('state')!='active' or r.get('tradability')!='tradable'):
            continue
        try:
            strike=_decimal(r['strike_price'])
            delta=abs(_decimal(r.get('quote',{}).get('delta')))
            if delta<=MAX_SHORT_DELTA:
                available[strike]=r
        except (ValueError,TypeError,KeyError,ArithmeticError):continue
    # Reject malformed opposite-wing data locally; an untrusted chain row must
    # never interrupt the existing position's mandatory exit path.
    wings={}
    for row in rows:
        if row.get('type','').upper()!=right or row.get('expiration_date')!=position['trade_date']:
            continue
        try:wings[_decimal(row['strike_price'])]=row
        except (KeyError,ValueError,TypeError,ArithmeticError):continue
    original=make_candidate(position)
    best=None
    for strike,short in available.items():
        if (right=='PUT' and strike>=min(original_strikes)) or (right=='CALL' and strike<=max(original_strikes)):
            continue
        wing_strike=strike-width if right=='PUT' else strike+width
        wing=wings.get(wing_strike)
        if not wing:continue
        new_legs=(OptionLeg(short['instrument_id'],short_opp,TradeSide.SELL,strike,position['trade_date'],1),
                  OptionLeg(wing['instrument_id'],short_opp,TradeSide.BUY,wing_strike,position['trade_date'],1))
        from dataclasses import replace
        from option_bot.domain import Money,StructureType
        supplemental=replace(original,legs=new_legs,net_credit=Money(Decimal('0.01')),
                             structure_type=StructureType.PUT_CREDIT_SPREAD if right=='PUT' else StructureType.CALL_CREDIT_SPREAD)
        try:
            net,fills,matched=quote_legs(supplemental,document,now)
            credit=-net
            if credit<MIN_PREMIUM:continue
            total_legs=original.legs+new_legs
            final_credit=opening+credit
            profile=PayoffProfile.evaluate(total_legs,final_credit,original.product.multiplier)
            # Preserve the original gross defined-risk ceiling and the daily cap.
            if profile.maximum_loss.amount>min(original_risk,max_risk) or profile.maximum_loss.amount<=0:continue
            score=profile.maximum_loss.amount
            candidate={'credit':credit,'legs':new_legs,'fills':fills,'matched':matched,
                       'profile':profile,'short_delta':str(short['quote']['delta']),
                       'old_risk':original_risk,'net_credit':final_credit,'max_risk':profile.maximum_loss.amount}
            if best is None or score<best['max_risk']:best=candidate
        except (ValueError,TypeError,KeyError,ArithmeticError):continue
    return best
