"""Prospective paper ledger for the corrected 2026 TFG strategy."""

import copy
import hashlib
import json
import math

import pandas as pd

from data import target_week


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _fractional_quantity(budget, buy_price, policy):
    precision = int(policy.get("share_precision", 6))
    if not 0 <= precision <= 8:
        raise ValueError("share_precision inválido")
    raw = budget / (buy_price * (1 + float(policy["commission"])))
    scale = 10 ** precision
    quantity = math.floor(raw * scale) / scale
    if quantity <= 0 or quantity * buy_price < float(policy.get("min_notional", 0)):
        return 0.0
    return quantity


def _validate_signal(signal):
    if signal.get("status") not in {
        "signal", "insufficient_technical_candidates",
        "insufficient_stage2_candidates", "no_data"
    }:
        raise ValueError("Estado de señal TFG inválido")
    if signal.get("status") == "signal":
        selections = signal.get("selections", [])
        if not selections:
            raise ValueError("Señal TFG sin selecciones")
        weights = [float(item["weight"]) for item in selections]
        if any(not math.isfinite(x) or x <= 0 for x in weights):
            raise ValueError("Peso TFG inválido")
        if sum(weights) > 1.000001:
            raise ValueError("Pesos TFG superan 100 %")


def _week_frames(panel, selections, signal_date):
    frames = {}
    expected_first = None
    expected_last = None
    for item in selections:
        ticker = item["ticker"]
        if ticker not in panel:
            raise ValueError("Ticker TFG sin datos: " + ticker)
        week = target_week(panel[ticker], signal_date)
        if week is None or week.empty:
            raise ValueError("Semana objetivo incompleta: " + ticker)
        first = week.index[0].date().isoformat()
        last = week.index[-1].date().isoformat()
        if expected_first is None:
            expected_first, expected_last = first, last
        if first != expected_first or last != expected_last:
            raise ValueError("Calendario inconsistente en cartera TFG: " + ticker)
        frames[ticker] = week
    if expected_first is None:
        return {}, None, None
    return frames, expected_first, expected_last


def _settle_week(config, panel, signal, nav_before):
    selections = signal.get("selections", [])
    if not selections:
        return {
            "signal_date": signal["asof"],
            "status": "cash_week",
            "entry_date": None,
            "exit_date": None,
            "exit_reason": "no_signal",
            "nav_before": nav_before,
            "nav_after": nav_before,
            "return_pct": 0.0,
            "positions": [],
        }

    policy = config["portfolio"]
    frames, first_session, last_session = _week_frames(panel, selections, signal["asof"])

    cash = float(nav_before)
    positions = []
    for item in selections:
        ticker = item["ticker"]
        raw_open = float(frames[ticker].iloc[0]["open"])
        buy_price = raw_open * (1 + float(policy["slippage"]))
        budget = nav_before * float(item["weight"])
        quantity = _fractional_quantity(budget, buy_price, policy)
        if quantity <= 0:
            continue
        buy_fee = quantity * buy_price * float(policy["commission"])
        outflow = quantity * buy_price + buy_fee
        if outflow > cash + 1e-6:
            raise ValueError("Caja TFG insuficiente para fill")
        cash -= outflow
        positions.append({
            "ticker": ticker,
            "weight_target": float(item["weight"]),
            "quantity": quantity,
            "entry_date": first_session,
            "raw_open": raw_open,
            "buy_price": buy_price,
            "buy_fee": buy_fee,
            "cost_basis": outflow,
        })

    if not positions:
        return {
            "signal_date": signal["asof"],
            "status": "cash_week",
            "entry_date": first_session,
            "exit_date": last_session,
            "exit_reason": "below_min_notional",
            "nav_before": nav_before,
            "nav_after": nav_before,
            "return_pct": 0.0,
            "positions": [],
        }

    common_dates = None
    for position in positions:
        dates = set(frames[position["ticker"]].index.date)
        common_dates = dates if common_dates is None else common_dates & dates
    dates = sorted(common_dates or [])
    if not dates or dates[0].isoformat() != first_session or dates[-1].isoformat() != last_session:
        raise ValueError("Faltan cierres comunes para evaluar stop TFG")

    stop = float(policy["portfolio_stop_pct"])
    exit_date = last_session
    exit_mode = "close"
    exit_reason = "week_end"
    stop_observed_date = None

    for index, day in enumerate(dates):
        value = cash
        for position in positions:
            frame = frames[position["ticker"]]
            row = frame.loc[frame.index.date == day]
            if row.empty:
                raise ValueError("Cierre TFG ausente: " + position["ticker"])
            value += position["quantity"] * float(row.iloc[-1]["close"])
        running_return = value / nav_before - 1
        if running_return <= stop:
            stop_observed_date = day.isoformat()
            if index + 1 < len(dates):
                exit_date = dates[index + 1].isoformat()
                exit_mode = "open"
                exit_reason = "portfolio_stop_next_open"
            else:
                exit_date = day.isoformat()
                exit_mode = "close"
                exit_reason = "portfolio_stop_at_week_end"
            break

    proceeds = cash
    for position in positions:
        frame = frames[position["ticker"]]
        row = frame.loc[frame.index.date == datetime_date(exit_date)]
        if row.empty:
            raise ValueError("Precio de salida TFG ausente: " + position["ticker"])
        raw_exit = float(row.iloc[0]["open"] if exit_mode == "open" else row.iloc[-1]["close"])
        sell_price = raw_exit * (1 - float(policy["slippage"]))
        sell_fee = position["quantity"] * sell_price * float(policy["commission"])
        received = position["quantity"] * sell_price - sell_fee
        proceeds += received
        position.update({
            "exit_date": exit_date,
            "exit_mode": exit_mode,
            "raw_exit": raw_exit,
            "sell_price": sell_price,
            "sell_fee": sell_fee,
            "net_pnl": received - position["cost_basis"],
            "net_return_pct": 100 * (received / position["cost_basis"] - 1),
        })

    return {
        "signal_date": signal["asof"],
        "status": "settled",
        "entry_date": first_session,
        "exit_date": exit_date,
        "stop_observed_date": stop_observed_date,
        "exit_reason": exit_reason,
        "nav_before": float(nav_before),
        "nav_after": float(proceeds),
        "return_pct": 100 * (proceeds / nav_before - 1),
        "positions": positions,
    }


def datetime_date(value):
    return pd.Timestamp(value).date()


def advance(config, panel, signal, state=None):
    _validate_signal(signal)
    config_hash = digest(config)
    signal_hash = digest(signal)
    asof = signal["asof"]
    capital = float(config["portfolio"]["capital"])

    if state is None:
        return {
            "schema_version": 1,
            "config_hash": config_hash,
            "currency": config["currency"],
            "first_signal_session": asof,
            "last_signal_session": asof,
            "signal_hash": signal_hash,
            "nav": capital,
            "pending_signal": copy.deepcopy(signal),
            "trades": [],
            "equity": [{"date": asof, "nav": capital, "decision_recorded": True}],
            "execution": {
                "fractional_shares": True,
                "share_precision": int(config["portfolio"]["share_precision"]),
                "min_notional": float(config["portfolio"]["min_notional"]),
                "commission": float(config["portfolio"]["commission"]),
                "slippage": float(config["portfolio"]["slippage"]),
                "portfolio_stop_pct": float(config["portfolio"]["portfolio_stop_pct"]),
            },
        }, True

    if state.get("config_hash") != config_hash:
        raise ValueError("El ledger TFG pertenece a otra configuración")
    if state["last_signal_session"] == asof:
        if state.get("signal_hash") != signal_hash:
            raise ValueError("Señal TFG revisada para una fecha ya registrada")
        return copy.deepcopy(state), False
    if state["last_signal_session"] > asof:
        raise ValueError("Señal TFG fuera de orden")

    result = copy.deepcopy(state)
    pending = result.get("pending_signal")
    if pending is not None:
        trade = _settle_week(config, panel, pending, float(result["nav"]))
        result["nav"] = float(trade["nav_after"])
        result["trades"].append(trade)

    result["last_signal_session"] = asof
    result["signal_hash"] = signal_hash
    result["pending_signal"] = copy.deepcopy(signal)
    result["equity"].append({
        "date": asof,
        "nav": float(result["nav"]),
        "decision_recorded": True,
    })
    return result, True
