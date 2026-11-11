"""Persistent local-only option simulation. No broker transport or credentials.

Natural fills: open longs at ask/shorts at bid; close longs at bid/shorts
at ask. Every leg must have an observed, recent quote and sufficient size.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from option_bot.session_expiration import expired_session_close
from option_bot.contract_metadata import enrich_contract
from option_bot.domain import (Decision, ExerciseStyle, LifecycleStatus, Money,
    OperatingMode, OptionLeg, OptionRight, Position, ProductMetadata,
    SettlementType, TradeCandidate, TradeSide, StructureType)
from option_bot.payoff import PayoffProfile
from option_bot.portfolio import PortfolioSelector
from option_bot.positions import PositionManager, PositionSnapshot

ET = ZoneInfo("America/New_York")
ZERO = Decimal("0")
from option_bot.probability import MINIMUM_PROBABILITY_OF_PROFIT
FLAGS = {"paper_only": True, "paper_trade_mode": True,
         "live_trading_enabled": False, "broker_execution_enabled": False,
         "order_submission_enabled": False, "order_placement_enabled": False,
         "paper_execution_mode": "LOCAL_SIMULATION"}


def _decimal(value):
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("NONFINITE_PRICE")
    return number


def _fresh(value, now):
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return timestamp.tzinfo is not None and -5 <= (now - timestamp).total_seconds() <= 60
    except (ValueError, TypeError):
        return False


def _atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".paper-", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _serialize_candidate(candidate, rows):
    return [{
        "contract_symbol": leg.contract_symbol,
        "instrument_id": rows[leg.contract_symbol]["instrument_id"],
        "right": leg.right.value, "side": leg.side.value, "strike": str(leg.strike),
        "expiration": leg.expiration, "quantity": leg.quantity,
    } for leg in candidate.legs]


def _candidate(position):
    product = position["product"]
    return TradeCandidate(position["candidate_id"], position["symbol"],
        tuple(OptionLeg(row["contract_symbol"], OptionRight(row["right"]), TradeSide(row["side"]),
                        Decimal(row["strike"]), row["expiration"], row["quantity"])
              for row in position["legs"]),
        ProductMetadata(position["symbol"], product["multiplier"],
                        ExerciseStyle(product["exercise_style"]),
                        SettlementType(product["settlement_type"]), product["last_trading_time"]),
        net_credit=Money(Decimal(position["entry_price"])) if position["premium_type"] == "CREDIT" else None,
        net_debit=Money(Decimal(position["entry_price"])) if position["premium_type"] == "DEBIT" else None,
        structure_type=StructureType(position["structure"]))


def _quote_legs(candidate, document, now, *, closing=False, held_legs=None):
    if (document.get("source") not in (("ROBINHOOD_MCP_RESEARCH", "ALPACA_MARKET_DATA") if closing else ("ROBINHOOD_MCP_RESEARCH",))
        or document.get("research_only") is not True
        or document.get("order_submission_enabled") is not False):
        raise ValueError("RESEARCH_GOVERNANCE_INVALID")
    if not _fresh(document.get("generated_at_utc"), now):
        raise ValueError("STALE_RESEARCH_SNAPSHOT")
    rows = document.get("symbols", {}).get(candidate.underlying_symbol, {}).get("contracts", [])
    contracts = {str(row.get("symbol")): row for row in rows if isinstance(row, dict)}
    by_id = {str(row.get("instrument_id")): row for row in rows if isinstance(row, dict)}
    held = {row["contract_symbol"]: row for row in held_legs or ()}
    net = ZERO
    fills = []
    matched = {}
    for leg in candidate.legs:
        stored = held.get(leg.contract_symbol)
        row = by_id.get(stored["instrument_id"]) if stored else (by_id.get(leg.contract_symbol) or contracts.get(leg.contract_symbol))
        if not row or not row.get("instrument_id"):
            raise ValueError("LEG_QUOTE_UNAVAILABLE")
        # Contract identity is preserved across entry and every subsequent mark/exit.
        if (row.get("expiration_date") != leg.expiration
            or str(row.get("type", "")).upper() != leg.right.value
            or _decimal(row.get("strike_price")) != leg.strike):
            raise ValueError("CONTRACT_IDENTITY_MISMATCH")
        if not closing and (row.get("state") != "active" or row.get("tradability") != "tradable"):
            raise ValueError("CONTRACT_NOT_TRADABLE")
        verified = enrich_contract(candidate.underlying_symbol, row)
        if (Decimal(str(verified["trade_value_multiplier"])) != candidate.product.multiplier
            or str(verified["exercise_style"]).upper() != candidate.product.exercise_style.value
            or bool(verified["settle_on_open"])):
            raise ValueError("CONTRACT_METADATA_MISMATCH")
        quote = row.get("quote", {})
        if quote.get("instrument_id") != row["instrument_id"]:
            raise ValueError("QUOTE_IDENTITY_MISMATCH")
        if not _fresh(quote.get("updated_at"), now):
            raise ValueError("STALE_RESEARCH_QUOTES")
        if not closing:
            required = ("delta", "gamma", "theta", "vega", "rho", "implied_volatility", "volume", "open_interest")
            if any(quote.get(field) is None for field in required):
                raise ValueError("RESEARCH_QUOTE_INCOMPLETE")
            for field in required:
                _decimal(quote[field])
        bid, ask = _decimal(quote.get("bid_price")), _decimal(quote.get("ask_price"))
        if bid <= ZERO or ask <= ZERO or ask < bid:
            raise ValueError("INVALID_LEG_QUOTE")
        side = ("SELL" if leg.side is TradeSide.BUY else "BUY") if closing else leg.side.value
        size = int(quote.get("ask_size" if side == "BUY" else "bid_size", 0))
        if size < leg.quantity:
            raise ValueError("INSUFFICIENT_QUOTED_SIZE")
        price = ask if side == "BUY" else bid
        net += price * leg.quantity * (1 if leg.side is TradeSide.BUY else -1)
        matched[leg.contract_symbol] = row
        fills.append({"contract_symbol": leg.contract_symbol, "instrument_id": row["instrument_id"],
                      "side": side, "quantity": leg.quantity, "price": str(price),
                      "quote_timestamp": quote["updated_at"], "simulated": True})
    return net, fills, matched


def _hold_to_expiry(position):
    """Only actual persisted entry deltas of every short credit leg grant exemption."""
    if position.get("premium_type") != "CREDIT":
        return False
    shorts = {row["instrument_id"] for row in position["legs"] if row["side"] == "SELL"}
    evidence = position.get("entry_short_deltas", [])
    if not shorts or {row.get("instrument_id") for row in evidence} != shorts:
        return False
    try:
        return all(abs(_decimal(row["delta"])) <= Decimal(".10") for row in evidence)
    except (ValueError, TypeError, KeyError, ArithmeticError):
        return False


class LocalPaperSimulation:
    def __init__(self, config):
        if not config.paper_only or config.order_submission_enabled:
            raise ValueError("LOCAL_PAPER_ONLY_REQUIRED")
        self.config = config
        self.path = config.database_path.parent / "option_001_paper_ledger.json"

    def cycle(self, evaluations, snapshot_path, now, *, allow_entries=True, force_close=False, force_expiry_holds=False):
        if now.tzinfo is None:
            raise ValueError("TIMEZONE_REQUIRED")
        now = now.astimezone(ET)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists():
                state = json.loads(self.path.read_text())
                if state.get("schema_version") != "1.0" or state.get("paper_only") is not True:
                    raise ValueError("PAPER_LEDGER_INVALID")
            else:
                state = {"schema_version": "1.0", **FLAGS, "open": [], "completed": [], "events": []}
            try:
                document = json.loads(Path(snapshot_path).read_text())
            except (OSError, ValueError):
                document = {}
            result = self._cycle(state, tuple(evaluations), document, now, allow_entries, force_close, force_expiry_holds)
            _atomic(self.path, state)
            observation_dir = self.path.parent / "position_observations"
            observation_dir.mkdir(parents=True, exist_ok=True)
            with (observation_dir / (now.date().isoformat() + ".jsonl")).open("a") as handle:
                observed = list(state["open"]) + [p for p in state["completed"] if p.get("closed_at") == now.isoformat()]
                for position in observed:
                    handle.write(json.dumps({"observed_at": now.isoformat(),
                        "position_id": position["position_id"], "symbol": position["symbol"],
                        "status": position["status"], "entry_price": position["entry_price"],
                        "current_price": position.get("current_price"),
                        "unrealized_pnl": position.get("unrealized_pnl"),
                        "realized_pnl": position.get("realized_pnl"),
                        "reason": position.get("exit_reason", position.get("last_reason")),
                        "legs": position["legs"],
                        "quote_evidence": document,
                        "paper_only": True, "order_submission_enabled": False}, default=str) + "\n")
            return result

    def _cycle(self, state, evaluations, document, now, allow_entries, force_close, force_expiry_holds):
        date = now.date().isoformat()
        cycle_events, rejected, selected, reasons = [], [], [], []
        degraded = False
        daily_pnl = sum((_decimal(p["realized_pnl"]) for p in state["completed"]
                         if str(p.get("closed_at", "")).startswith(date) and p.get("realized_pnl") is not None), ZERO)
        manager = PositionManager(mandatory_exit=self.config.mandatory_exit)
        for position in list(state["open"]):
            hold_to_expiry = _hold_to_expiry(position)
            requested_close = force_close and (not hold_to_expiry or force_expiry_holds)
            try:
                session_close = expired_session_close(position, now)
                if session_close is not None:
                    position.update(status="EXPIRED", closed_at=session_close.isoformat(),
                        expiration_processed_at=now.isoformat(), exit_price=None,
                        current_price=None, realized_pnl=None, unrealized_pnl=None,
                        settlement_status="PENDING", settlement_reason="OFFICIAL_EXPIRATION_VALUE_REQUIRED",
                        exit_reason="NY_SESSION_CLOSE_PAPER_EXPIRATION", exit_fills=[], exit_pending=False)
                    state["open"].remove(position)
                    state["completed"].append(position)
                    event = {**FLAGS, "action": "PAPER_EXPIRE", "position_id": position["position_id"],
                        "symbol": position["symbol"], "observed_at": now.isoformat(),
                        "effective_at": session_close.isoformat(), "reason": position["exit_reason"],
                        "settlement_status": "PENDING", "fills": [], "realized_pnl": None}
                    state["events"].append(event)
                    cycle_events.append(event)
                    continue
                candidate = _candidate(position)
                net, fills, _ = _quote_legs(candidate, document, now, closing=True, held_legs=position["legs"])
                liquidation = net if position["premium_type"] == "DEBIT" else -net
                opening = _decimal(position["entry_price"])
                pnl = ((liquidation - opening) if position["premium_type"] == "DEBIT"
                       else (opening - liquidation)) * candidate.product.multiplier
                position.update(status="OPEN", current_price=str(liquidation),
                                unrealized_pnl=str(pnl.quantize(Decimal(".01"))),
                                last_quote_at=now.isoformat(), last_reason="THESIS_INTACT", exit_pending=False)
                # Barney's experimental defensive condor: only before the
                # ordinary stop, with actual separately quoted opposite legs.
                # The original stop stays authoritative after adjustment.
                if (not requested_close and not hold_to_expiry
                    and daily_pnl > -self.config.max_daily_defined_loss):
                    from option_bot.defensive_condor import candidates as defensive_candidates
                    try:
                        defense=defensive_candidates(position,document,now,_quote_legs,_candidate,
                            min(self.config.loss_limit_for(position['symbol']),
                                self.config.max_daily_defined_loss))
                    except (ValueError,KeyError,TypeError,ArithmeticError):
                        # Defense data failure must not suppress the original stop.
                        defense=None
                    if defense is not None:
                        new_legs=[{'contract_symbol':leg.contract_symbol,
                                   'instrument_id':defense['matched'][leg.contract_symbol]['instrument_id'],
                                   'right':leg.right.value,'side':leg.side.value,
                                   'strike':str(leg.strike),'expiration':leg.expiration,
                                   'quantity':leg.quantity} for leg in defense['legs']]
                        previous_credit=position['entry_price']
                        proposed={**position,'legs':list(position['legs'])+new_legs,
                            'structure':'IRON_CONDOR','entry_price':str(defense['net_credit'])}
                        try:
                            combined=_candidate(proposed)
                            combined_net,combined_fills,_=_quote_legs(combined,document,now,
                                closing=True,held_legs=proposed['legs'])
                        except (ValueError,TypeError,KeyError,ArithmeticError):
                            combined=None
                        if combined is None:
                            # No partial paper leg addition: respect normal exit.
                            defense=None
                    if defense is not None:
                        position['legs'].extend(new_legs)
                        position['structure']='IRON_CONDOR'
                        position['entry_price']=str(defense['net_credit'].quantize(Decimal('.01')))
                        position['maximum_loss']=str(defense['profile'].maximum_loss.amount)
                        position['maximum_profit']=str(defense['profile'].maximum_profit.amount)
                        position['defensive_adjustment']={
                            'status':'PAPER_FILLED','strategy':'OPPOSITE_CREDIT_TO_IRON_CONDOR',
                            'adjusted_at':now.isoformat(),'original_credit':previous_credit,
                            'added_credit':str(defense['credit']),
                            'original_maximum_loss':str(defense['old_risk']),
                            'new_maximum_loss':str(defense['max_risk']),
                            'added_legs':new_legs,'entry_fills':defense['fills'],
                            'cutoff_central':'12:30','paper_only':True,
                            'broker_submissions':0}
                        position.setdefault('entry_fills',[]).extend(defense['fills'])
                        position.setdefault('entry_short_deltas',[]).append({
                            'instrument_id':new_legs[0]['instrument_id'],
                            'strike':new_legs[0]['strike'],
                            'delta':defense['short_delta']})
                        event={**FLAGS,'action':'PAPER_DEFENSIVE_ADJUST',
                            'position_id':position['position_id'],'symbol':position['symbol'],
                            'observed_at':now.isoformat(),
                            'new_structure':'IRON_CONDOR','additional_credit':str(defense['credit']),
                            'new_maximum_loss':str(defense['max_risk']),
                            'fills':defense['fills']}
                        state['events'].append(event)
                        cycle_events.append(event)
                        # This combined mark was verified BEFORE any ledger
                        # mutation, preserving the original stop on failures.
                        candidate=combined
                        liquidation=-combined_net
                        opening=_decimal(position['entry_price'])
                        pnl=(opening-liquidation)*candidate.product.multiplier
                        position.update(current_price=str(liquidation),
                            unrealized_pnl=str(pnl.quantize(Decimal('.01'))))
                action = manager.evaluate(Position(position["position_id"], candidate,
                    datetime.fromisoformat(position["opened_at"]), entry_price=Money(opening)),
                    PositionSnapshot(True, liquidation, ZERO, True, Decimal("-1"),
                                     daily_pnl <= -self.config.max_daily_defined_loss), now, hold_to_expiry=hold_to_expiry)
                position["last_reason"] = action.reason_code
                if action.action == "CLOSE" or requested_close:
                    reason = action.reason_code if action.action == "CLOSE" else "PAPER_CLOSE_REQUEST"
                    position.update(status="CLOSED", closed_at=now.isoformat(), exit_price=str(liquidation),
                        realized_pnl=str(pnl.quantize(Decimal(".01"))), unrealized_pnl="0.00",
                        exit_reason=reason, exit_fills=fills)
                    state["open"].remove(position)
                    state["completed"].append(position)
                    daily_pnl += pnl
                    event = {**FLAGS, "action": "PAPER_CLOSE", "position_id": position["position_id"],
                             "symbol": position["symbol"], "observed_at": now.isoformat(),
                             "reason": reason, "fills": fills, "realized_pnl": position["realized_pnl"]}
                    state["events"].append(event)
                    cycle_events.append(event)
            except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                position.update(status="DEGRADED", last_reason=str(exc), current_price=None,
                                unrealized_pnl=None, last_checked_at=now.isoformat(),
                                exit_pending=requested_close or (not hold_to_expiry and now.time().replace(tzinfo=None) >= self.config.mandatory_exit))
                degraded = True
                reasons.append("OPEN_POSITION_QUOTE_UNAVAILABLE")
        day_trades = [p for p in state["open"] + state["completed"] if p["trade_date"] == date]
        count = len(day_trades)
        used = sum((_decimal(p["maximum_loss"]) for p in day_trades), ZERO)
        minute = now.time().replace(second=0, microsecond=0, tzinfo=None)
        within_window = now.weekday() < 5 and self.config.entry_start <= minute <= self.config.entry_end
        if allow_entries and not within_window:
            reasons.append("OUTSIDE_ENTRY_WINDOW")
        if daily_pnl <= -self.config.max_daily_defined_loss:
            reasons.append("DAILY_STOP")
        if allow_entries and within_window and not degraded and daily_pnl > -self.config.max_daily_defined_loss:
            executable = []
            by_id = {}
            for item in evaluations:
                if item.decision is not Decision.TRADE or item.trade_candidate is None or item.candidate is None:
                    continue
                try:
                    candidate = item.trade_candidate
                    if (item.symbol not in self.config.symbols or item.symbol != candidate.underlying_symbol
                        or candidate.operating_mode is not OperatingMode.PAPER
                        or any(leg.expiration != date for leg in candidate.legs)):
                        raise ValueError("CANDIDATE_IDENTITY_OR_EXPIRATION_INVALID")
                    if item.symbol in {p["symbol"] for p in day_trades}:
                        raise ValueError("DUPLICATE_DAILY_ENTRY")
                    if item.candidate.exposure_group in {p["exposure_group"] for p in state["open"]} and not item.candidate.correlation_justified:
                        raise ValueError("CORRELATED_EXPOSURE")
                    if item.probability_of_profit is None or not item.probability_model_version:
                        raise ValueError("PROBABILITY_OF_PROFIT_UNAVAILABLE")
                    if item.probability_of_profit < MINIMUM_PROBABILITY_OF_PROFIT:
                        raise ValueError("PROBABILITY_OF_PROFIT_BELOW_MINIMUM")
                    net, fills, rows = _quote_legs(candidate, document, now)
                    premium = net if candidate.net_debit is not None else -net
                    if premium <= ZERO:
                        raise ValueError("NONPOSITIVE_OPENING_PREMIUM")
                    # Do not assume an optimistic midpoint limit can fill.
                    limit = item.candidate.entry_price
                    if limit is not None and ((candidate.net_debit is not None and premium > limit)
                                              or (candidate.net_credit is not None and premium < limit)):
                        raise ValueError("NATURAL_PRICE_OUTSIDE_ENTRY_LIMIT")
                    profile = (PayoffProfile.evaluate_debit(candidate.legs, premium, candidate.product.multiplier)
                               if candidate.net_debit is not None else
                               PayoffProfile.evaluate(candidate.legs, premium, candidate.product.multiplier))
                    if profile.maximum_loss.amount <= ZERO or profile.maximum_profit.amount <= ZERO:
                        raise ValueError("INVALID_DEFINED_RISK_PAYOFF")
                    if profile.maximum_loss.amount > self.config.loss_limit_for(item.symbol):
                        raise ValueError("MAX_LOSS_LIMIT")
                    if (candidate.structure_type in {StructureType.PUT_CREDIT_SPREAD, StructureType.CALL_CREDIT_SPREAD}
                        and profile.maximum_profit.amount < profile.maximum_loss.amount * Decimal(".15")):
                        raise ValueError("PROFIT_TO_MAX_LOSS_BELOW_MINIMUM")
                    corrected = replace(item.candidate, maximum_loss=profile.maximum_loss.amount,
                                        maximum_profit=profile.maximum_profit.amount, entry_price=premium)
                    executable.append(corrected)
                    by_id[candidate.candidate_id] = (item, premium, profile, fills, rows)
                except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                    rejected.append({"symbol": item.symbol, "reason": str(exc)})
            selection = PortfolioSelector(self.config.max_daily_entries, self.config.max_daily_defined_loss).select(
                executable, [p["symbol"] for p in state["open"]], used, count)
            reasons.extend(selection.reason_codes)
            rejected.extend({"symbol": symbol, "reason": reason} for symbol, reason in selection.rejected.items())
            for choice in selection.selected:
                item, premium, profile, fills, rows = by_id[choice.candidate_id]
                candidate = item.trade_candidate
                legs = _serialize_candidate(candidate, rows)
                identity = json.dumps([date, item.symbol, legs], sort_keys=True)
                position_id = "PAPER-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
                position = {**FLAGS, "position_id": position_id, "candidate_id": candidate.candidate_id,
                    "symbol": item.symbol, "trade_date": date, "opened_at": now.isoformat(), "status": "OPEN",
                    "structure": candidate.structure_type.value,
                    "premium_type": "DEBIT" if candidate.net_debit is not None else "CREDIT",
                    "entry_price": str(premium.quantize(Decimal(".01"))), "quantity": 1,
                    "maximum_loss": str(profile.maximum_loss.amount), "maximum_profit": str(profile.maximum_profit.amount),
                    "exposure_group": choice.exposure_group, "evidence_id": item.evidence_id,
                    "probability_of_profit": str(item.probability_of_profit),
                    "probability_model_version": item.probability_model_version,
                    "minimum_probability_of_profit": str(MINIMUM_PROBABILITY_OF_PROFIT),
                    "entry_reason": "QUALIFIED_STRATEGY_LOCAL_PAPER_FILL",
                    "snapshot_generated_at": document["generated_at_utc"], "legs": legs, "entry_fills": fills,
                    "product": {"multiplier": candidate.product.multiplier,
                                "exercise_style": candidate.product.exercise_style.value,
                                "settlement_type": candidate.product.settlement_type.value,
                                "last_trading_time": candidate.product.last_trading_time},
                    "current_price": None, "unrealized_pnl": None}
                position["entry_short_deltas"] = [
                    {"instrument_id": rows[leg.contract_symbol]["instrument_id"],
                     "strike": str(leg.strike), "delta": str(rows[leg.contract_symbol]["quote"]["delta"])}
                    for leg in candidate.legs if leg.side is TradeSide.SELL]
                position["exit_policy"] = "LOW_DELTA_HOLD_TO_EXPIRY_V1" if _hold_to_expiry(position) else "STANDARD_EXITS"
                state["open"].append(position)
                event = {**FLAGS, "action": "PAPER_OPEN", "position_id": position_id,
                         "symbol": item.symbol, "observed_at": now.isoformat(),
                         "reason": position["entry_reason"], "fills": fills}
                state["events"].append(event)
                cycle_events.append(event)
                selected.append({"symbol": choice.symbol, "candidate_id": choice.candidate_id,
                                 "structure": choice.structure_type.value, "premium_type": position["premium_type"],
                                 "entry_price": position["entry_price"], "maximum_loss": position["maximum_loss"],
                                 "maximum_profit": position["maximum_profit"], "rank_score": str(choice.rank_score),
                                 "probability_of_profit": position["probability_of_profit"],
                                 "probability_model_version": position["probability_model_version"]})
                count += 1
                used += profile.maximum_loss.amount
        state["generated_at_utc"] = now.isoformat()
        return {**FLAGS, "trade_date": date, "generated_at_utc": now.isoformat(),
            "open": list(state["open"]), "completed": list(state["completed"]), "selected": selected,
            "new_events": cycle_events, "execution_rejections": rejected,
            "paper_execution_reasons": sorted(set(reasons)),
            "daily_entry_count": count, "daily_defined_loss": str(used.quantize(Decimal(".01"))),
            "daily_risk_remaining": str(max(ZERO, self.config.max_daily_defined_loss-used).quantize(Decimal(".01"))),
            "daily_realized_pnl": str(daily_pnl.quantize(Decimal(".01"))),
            "realized_pnl": str(sum((_decimal(p["realized_pnl"]) for p in state["completed"] if p.get("realized_pnl") is not None), ZERO).quantize(Decimal(".01"))),
            "settlement_pending_count": sum(p.get("settlement_status") == "PENDING" for p in state["completed"]),
            "snapshot_fresh": _fresh(document.get("generated_at_utc"), now),
            "paper_execution_status": "DEGRADED" if degraded else "AVAILABLE"}
