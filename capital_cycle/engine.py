"""Stateful monthly capital-cycle paper portfolio with next-open execution."""

from __future__ import annotations

import copy
import hashlib
import json
import math


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _fractional_quantity(notional, price, policy):
    if notional <= 0 or price <= 0:
        return 0.0
    commission = float(policy["commission"])
    if not policy.get("fractional_shares", True):
        return float(math.floor(notional / (price * (1 + commission))))
    precision = int(policy.get("share_precision", 6))
    scale = 10 ** precision
    raw = notional / (price * (1 + commission))
    quantity = math.floor(raw * scale) / scale
    if quantity <= 0 or quantity * price < float(policy.get("min_notional", 0)):
        return 0.0
    return quantity


def _event(state, kind, asof, ticker=None, **fields):
    state["events"].append({"type": kind, "date": asof, "ticker": ticker, **fields})
    state["events"] = state["events"][-4000:]


def _apply_corporate_actions(state, bars, asof):
    for ticker, position in list(state["positions"].items()):
        bar = bars[ticker]
        split = float(bar.get("split", 0) or 0)
        if split:
            position["quantity"] *= split
            position["entry_price"] /= split
            _event(state, "split", asof, ticker, ratio=split)
        dividend = float(bar.get("dividend", 0) or 0)
        if dividend:
            amount = dividend * position["quantity"]
            state["cash"] += amount
            _event(state, "dividend", asof, ticker, amount=amount, per_share=dividend)


def _open_nav(state, bars):
    return state["cash"] + sum(
        position["quantity"] * bars[ticker]["open"]
        for ticker, position in state["positions"].items()
    )


def _sell_quantity(state, ticker, quantity, bar, asof, policy, reason):
    position = state["positions"][ticker]
    quantity = min(float(quantity), float(position["quantity"]))
    if quantity <= 0:
        return
    price = float(bar["open"]) * (1 - float(policy["slippage"]))
    gross = quantity * price
    fee = gross * float(policy["commission"])
    state["cash"] += gross - fee
    position["quantity"] -= quantity
    _event(state, "fill", asof, ticker, side="sell", quantity=quantity,
           price=price, fee=fee, reason=reason)
    if position["quantity"] <= 1e-10:
        del state["positions"][ticker]


def _buy_quantity(state, ticker, quantity, bar, asof, policy, sector, reason):
    if quantity <= 0:
        return
    price = float(bar["open"]) * (1 + float(policy["slippage"]))
    maximum = state["cash"] / (price * (1 + float(policy["commission"])))
    quantity = min(quantity, maximum)
    precision = int(policy.get("share_precision", 6))
    scale = 10 ** precision
    quantity = math.floor(quantity * scale) / scale
    if quantity <= 0 or quantity * price < float(policy.get("min_notional", 0)):
        _event(state, "skip", asof, ticker, reason="below_min_notional")
        return
    gross = quantity * price
    fee = gross * float(policy["commission"])
    state["cash"] -= gross + fee
    if ticker in state["positions"]:
        old = state["positions"][ticker]
        total_qty = old["quantity"] + quantity
        old["entry_price"] = (old["entry_price"] * old["quantity"] + price * quantity) / total_qty
        old["quantity"] = total_qty
    else:
        state["positions"][ticker] = {
            "quantity": quantity,
            "entry_price": price,
            "entry_date": asof,
            "sector": sector,
        }
    _event(state, "fill", asof, ticker, side="buy", quantity=quantity,
           price=price, fee=fee, reason=reason)


def _settle_pending(state, bars, asof, policy):
    pending = state.get("pending")
    if not pending:
        return
    expected = pending.get("expected_fill_session")
    if expected and asof != expected:
        raise ValueError(f"Orden mensual no liquidada en la apertura prevista: {expected}; sesión actual {asof}")
    targets = pending["target_weights"]
    sectors = pending.get("sectors", {})
    nav = _open_nav(state, bars)

    # Sell reductions first to make cash available.
    for ticker in sorted(list(state["positions"])):
        target = float(targets.get(ticker, 0.0))
        current_value = state["positions"][ticker]["quantity"] * bars[ticker]["open"]
        desired_value = nav * target
        if current_value > desired_value + float(policy.get("min_notional", 0)):
            quantity = (current_value - desired_value) / max(float(bars[ticker]["open"]), 1e-12)
            _sell_quantity(state, ticker, quantity, bars[ticker], asof, policy, "monthly_rebalance")

    nav = _open_nav(state, bars)
    for ticker, target in sorted(targets.items()):
        target = float(target)
        if target <= 0:
            continue
        current_qty = state["positions"].get(ticker, {}).get("quantity", 0.0)
        current_value = current_qty * bars[ticker]["open"]
        desired_value = nav * target
        gap = desired_value - current_value
        if gap <= float(policy.get("min_notional", 0)):
            continue
        buy_price = float(bars[ticker]["open"]) * (1 + float(policy["slippage"]))
        quantity = _fractional_quantity(gap, buy_price, policy)
        _buy_quantity(state, ticker, quantity, bars[ticker], asof, policy,
                      sectors.get(ticker, ""), "monthly_rebalance")
    _event(state, "rebalance_filled", asof, reason="next_open",
           signal_date=pending["signal_date"], targets=len(targets))
    state["pending"] = None


def _mark(state, bars, asof, benchmark_close):
    nav = state["cash"] + sum(
        position["quantity"] * bars[ticker]["close"]
        for ticker, position in state["positions"].items()
    )
    if not math.isfinite(nav) or nav < 0:
        raise ValueError("NAV capital-cycle inválido")
    state["nav"] = nav
    state["equity"].append({
        "date": asof,
        "nav": nav,
        "cash": state["cash"],
        "positions": len(state["positions"]),
        "benchmark_close": float(benchmark_close),
    })
    state["equity"] = state["equity"][-1500:]
    if state.get("benchmark_first_close") is None:
        state["benchmark_first_close"] = float(benchmark_close)
    state["benchmark_last_close"] = float(benchmark_close)


def advance(config, bars, asof, benchmark_close, decision=None, state=None):
    """Advance one fully closed XNYS session.

    A decision is made at a close and stored as pending target weights. Fills
    happen only at the explicitly recorded next session's open.
    """
    policy = config["paper_policy"]
    config_hash = digest(config)
    bar_hash = digest({ticker: bars[ticker] for ticker in sorted(bars)})

    if state is None:
        state = {
            "schema_version": 1,
            "strategy_id": "capital_cycle_inflection_2026",
            "config_hash": config_hash,
            "currency": config["currency"],
            "source": "yfinance/raw_ohlc+actions/current_fundamentals",
            "first_session": asof,
            "last_session": None,
            "first_signal_session": None,
            "last_signal_session": None,
            "cash": float(policy["capital"]),
            "nav": float(policy["capital"]),
            "positions": {},
            "pending": None,
            "equity": [],
            "signals": [],
            "events": [],
            "market_hashes": {},
            "benchmark_first_close": None,
            "benchmark_last_close": None,
        }
    else:
        if state.get("config_hash") != config_hash:
            raise ValueError("Configuración capital-cycle modificada: iniciar campaña nueva")
        if state.get("strategy_id") != "capital_cycle_inflection_2026":
            raise ValueError("Diario capital-cycle no reconocido")
        if state.get("last_session") == asof:
            # The ledger is append-only. A provider may revise an already frozen
            # OHLC row after the first successful run; duplicate executions must
            # remain a clean no-op instead of rewriting or failing the campaign.
            return copy.deepcopy(state), False
        if state.get("last_session") and state["last_session"] > asof:
            raise ValueError("Sesión capital-cycle fuera de orden")

    result = copy.deepcopy(state)
    required = set(result["positions"])
    if result.get("pending"):
        required |= set(result["pending"]["target_weights"])
    missing = sorted(required - set(bars))
    if missing:
        raise ValueError("Faltan barras para posiciones/órdenes: " + ",".join(missing))

    _apply_corporate_actions(result, bars, asof)
    _settle_pending(result, bars, asof, policy)
    _mark(result, bars, asof, benchmark_close)

    if decision is not None:
        if decision.get("signal_date") != asof:
            raise ValueError("La decisión debe pertenecer al cierre actual")
        if result.get("pending"):
            raise ValueError("Existe una orden pendiente sin liquidar")
        targets = decision.get("target_weights") or {}
        if any(not isinstance(ticker, str) or not 0 <= float(weight) <= 1 for ticker, weight in targets.items()):
            raise ValueError("Pesos objetivo inválidos")
        if sum(float(x) for x in targets.values()) > float(policy["invest_fraction"]) + 1e-9:
            raise ValueError("Exposición objetivo superior al límite")
        result["pending"] = {
            "signal_date": asof,
            "expected_fill_session": decision["expected_fill_session"],
            "target_weights": {ticker: float(weight) for ticker, weight in targets.items()},
            "sectors": dict(decision.get("sectors") or {}),
        }
        signal = {
            "date": asof,
            "expected_fill_session": decision["expected_fill_session"],
            "coverage": decision.get("coverage"),
            "target_weights": result["pending"]["target_weights"],
            "selected": decision.get("selected", []),
            "sector_scores": decision.get("sector_scores", {}),
            "excluded_count": decision.get("excluded_count"),
            "exit_reasons": decision.get("exit_reasons", {}),
        }
        result["signals"].append(signal)
        result["signals"] = result["signals"][-60:]
        if result["first_signal_session"] is None:
            result["first_signal_session"] = asof
        result["last_signal_session"] = asof
        _event(result, "signal", asof, targets=len(targets),
               expected_fill_session=decision["expected_fill_session"])

    result["last_session"] = asof
    result["market_hashes"][asof] = bar_hash
    result["market_hashes"] = dict(list(sorted(result["market_hashes"].items()))[-90:])
    return result, True


def benchmark_return_pct(state):
    first = state.get("benchmark_first_close")
    last = state.get("benchmark_last_close")
    if not first or not last:
        return None
    return 100.0 * (float(last) / float(first) - 1.0)
