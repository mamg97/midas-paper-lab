"""Prospective daily paper bookkeeping for frozen WEEKLY ML signals.

The historical weekly ledger is never mutated here. No past open is replayed
when the daily execution window was missed. All prices are RAW unadjusted OHLC.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paper import BENCHMARKS, _fractional_quantity, _select, digest, strategy_ids

FIRST_DAILY_SIGNAL = "2026-10-09"
ENGINE_VERSION = "weekly_ml_daily_next_open_v1"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


def _check_config(state, config):
    if (state.get("schema_version") != 1
            or state.get("engine") != ENGINE_VERSION
            or state.get("config_hash") != digest(config)
            or set(state.get("strategies", {})) != set(strategy_ids(config))):
        raise ValueError("Diario daily ML ajeno a campaña o configuración")


def freeze_signal(config, forecast, state=None):
    """Called AFTER Friday's frozen weekly forecast was saved, before next open."""
    day = forecast["asof"]
    if day < FIRST_DAILY_SIGNAL:
        return state, False
    if forecast.get("config_hash") != digest(config):
        raise ValueError("Forecast weekly ML de otra configuración")
    if set(forecast.get("models", {})) != set(config["models"]):
        raise ValueError("Forecast weekly ML incompleto")
    if state is not None:
        _check_config(state, config)
        if day == state["last_signal_session"]:
            if state["signal_hash"] != digest(forecast):
                raise ValueError("La señal congelada fue revisada")
            return state, False
        if day < state["last_signal_session"]:
            raise ValueError("No se pueden congelar señales antiguas")
        if state["last_session"] != day:
            raise ValueError("Falta liquidar o valorar el cierre anterior a la nueva señal")
        for book in state["strategies"].values():
            if book["positions"] or book["pending"]:
                raise ValueError("No se puede emitir nueva señal con cartera anterior sin liquidar")
        result = copy.deepcopy(state)
    else:
        capital = float(config["paper_policy"]["capital"])
        result = {
            "schema_version": 1, "engine": ENGINE_VERSION,
            "config_hash": digest(config), "currency": config["currency"],
            "initial_capital": capital, "first_session": day,
            "last_session": day, "last_signal_session": day,
            "signal_hash": digest(forecast), "strategies": {},
            "gap_sessions": [], "execution_model": "paper_open_recorded_after_session_close"
        }
        for name in strategy_ids(config):
            result["strategies"][name] = {
                "cash": capital, "nav": capital, "positions": {},
                "pending": [], "trades": [], "events": [],
                "equity": [{"date": day, "nav": capital, "decision_recorded": True}]
            }
    result["last_signal_session"] = day
    result["signal_hash"] = digest(forecast)
    for name, book in result["strategies"].items():
        selected = _select(name, forecast["models"].get(name, {}), config["paper_policy"], day)
        book["pending"] = selected
        book["events"].append({"date": day, "type": "signal_frozen", "count": len(selected)})
    return result, True


def _price(prices, ticker, key):
    row = prices.get(ticker)
    if not isinstance(row, dict) or key not in row:
        raise ValueError(f"Barra OHLC ausente: {ticker}")
    n = float(row[key])
    if not math.isfinite(n) or n <= 0:
        raise ValueError(f"Precio no válido: {ticker} {key}")
    return n


def process_day(config, state, day, prices, *, previous_session, first_after_signal, week_end):
    """Pure, atomic daily transition. Caller verifies NYSE calendar and vendor freshness."""
    _check_config(state, config)
    if day <= state["last_session"]:
        return copy.deepcopy(state), False
    if state["last_session"] != previous_session:
        raise ValueError("Sesión perdida: no reconstruir fills o NAV retroactivamente")
    if day <= state["last_signal_session"]:
        raise ValueError("La valoración precede a la señal")
    policy = config["paper_policy"]
    result = copy.deepcopy(state)
    for name, book in result["strategies"].items():
        pending = book["pending"]
        if pending:
            if not first_after_signal or state["last_session"] != state["last_signal_session"]:
                raise ValueError("Apertura semanal no ejecutada en ventana prospectiva")
        if first_after_signal and pending:
            previous_nav = float(book["nav"])
            budget = previous_nav * float(policy["invest_fraction"])
            if name not in BENCHMARKS:
                budget = min(previous_nav * float(policy["max_entry_weight"]),
                             budget / len(pending))
            for order in pending:
                ticker = order["ticker"]
                entry = _price(prices, ticker, "open") * (1 + float(policy["slippage"]))
                shares = _fractional_quantity(budget, entry, policy)
                if shares <= 0:
                    book["events"].append({"date": day, "type": "unfilled",
                                           "ticker": ticker, "reason": "below_min_notional"})
                    continue
                fee = entry * shares * float(policy["commission"])
                if entry * shares + fee > book["cash"] + 1e-7:
                    raise ValueError("Caja insuficiente para la compra paper")
                if ticker in book["positions"]:
                    raise ValueError("Posición duplicada")
                book["positions"][ticker] = {
                    "shares": shares, "entry_price": entry, "entry_fee": fee,
                    "signal_date": order["signal_date"], "entry_date": day
                }
                book["cash"] -= entry * shares + fee
                book["events"].append({"date": day, "type": "buy",
                    "ticker": ticker, "shares": shares, "price": entry, "fee": fee,
                    "execution": "simulated_next_open"})
            book["pending"] = []
        # Missing bar -> abort entire atomic transaction. Never silently ffill.
        marks = {ticker: _price(prices, ticker, "close")
                 for ticker in book["positions"]}
        if week_end:
            for ticker, position in list(book["positions"].items()):
                shares = position["shares"]
                exit_price = marks[ticker] * (1 - float(policy["slippage"]))
                fee = exit_price * shares * float(policy["commission"])
                received = shares * exit_price - fee
                book["cash"] += received
                net_pnl = received - position["entry_price"] * shares - position["entry_fee"]
                book["trades"].append({
                    "ticker": ticker, "signal_date": position["signal_date"],
                    "entry_date": position["entry_date"], "exit_date": day,
                    "shares": shares, "buy_price": position["entry_price"],
                    "sell_price": exit_price, "buy_commission": position["entry_fee"],
                    "sell_commission": fee, "net_pnl": net_pnl
                })
                book["events"].append({"date": day, "type": "sell",
                    "ticker": ticker, "shares": shares, "price": exit_price,
                    "fee": fee, "execution": "simulated_week_close"})
            book["positions"] = {}
        nav = book["cash"] + sum(float(pos["shares"]) * marks[ticker]
                                  for ticker, pos in book["positions"].items())
        if not math.isfinite(nav) or nav < 0:
            raise ValueError("NAV paper diario inválido")
        book["nav"] = nav
        book["equity"].append({"date": day, "nav": nav, "decision_recorded": False})
    result["last_session"] = day
    return result, True


def live_calendar(now=None):
    import pandas_market_calendars as mcal
    import pandas as pd
    now = now or datetime.now(timezone.utc)
    schedule = mcal.get_calendar("XNYS").schedule(
        start_date=(now - timedelta(days=17)).date(),
        end_date=(now + timedelta(days=9)).date())
    eligible = [str(day.date()) for day, row in schedule.iterrows()
                if now >= row["market_close"].to_pydatetime() + timedelta(minutes=90)]
    if not eligible:
        return None
    day = eligible[-1]
    future = schedule.loc[schedule.index.date > datetime.fromisoformat(day).date()]
    if future.empty or now >= future.iloc[0]["market_open"].to_pydatetime():
        raise ValueError("Valoración fuera de la ventana antes de siguiente apertura")
    days = [str(d.date()) for d in schedule.index]
    index = days.index(day)
    previous = days[index - 1]
    next_day = days[index + 1]
    week_end = pd.Timestamp(day).to_period("W-FRI") != pd.Timestamp(next_day).to_period("W-FRI")
    return day, previous, next_day, week_end


def download_bars(tickers, day):
    if not tickers:
        return {}
    import yfinance as yf
    import pandas as pd
    ordered = sorted(set(tickers))
    raw = yf.download(ordered,
                      start=(datetime.fromisoformat(day) - timedelta(days=4)).date().isoformat(),
                      end=(datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat(),
                      interval="1d", auto_adjust=False, actions=False,
                      group_by="ticker", threads=True, progress=False)
    if raw is None or raw.empty:
        raise ValueError("Proveedor de barras vacío")
    prices = {}
    for ticker in ordered:
        if isinstance(raw.columns, pd.MultiIndex):
            if ticker not in raw.columns.get_level_values(0):
                raise ValueError("Barra faltante del proveedor: " + ticker)
            frame = raw[ticker]
        else:
            if len(ordered) != 1:
                raise ValueError("Datos sin identificar ticker")
            frame = raw
        frame = frame[frame.index.strftime("%Y-%m-%d") == day]
        if len(frame) != 1:
            raise ValueError("No hay cierre oficial del día para " + ticker)
        row = frame.iloc[0]
        prices[ticker] = {"open": float(row["Open"]), "close": float(row["Close"])}
        _price(prices, ticker, "open")
        _price(prices, ticker, "close")
    return prices


def run(config_path, forecast_dir, output, phase):
    config = read(config_path)
    output = Path(output)
    state = read(output) if output.exists() else None
    if phase == "signal":
        files = sorted(Path(forecast_dir).glob("????-??-??.json"))
        if not files:
            return {"status": "no_forecast"}
        forecast = read(files[-1])
        state, changed = freeze_signal(config, forecast, state)
        if changed:
            write(output, state)
        return {"status": "signal_frozen" if changed else "already_frozen",
                "session": forecast["asof"], "changed": changed}
    if phase != "daily":
        raise ValueError("Fase desconocida")
    if state is None:
        return {"status": "waiting_for_first_new_signal", "changed": False}
    calendar = live_calendar()
    if calendar is None:
        return {"status": "market_not_closed", "changed": False}
    day, previous, next_day, week_end = calendar
    if day <= state["last_session"]:
        return {"status": "already_recorded", "session": day, "changed": False}
    first = state["last_session"] == state["last_signal_session"]
    if first and previous != state["last_signal_session"]:
        raise ValueError("Primera apertura perdida; nunca hacer backfill")
    tickers = {x for book in state["strategies"].values()
               for x in list(book["positions"]) + [p["ticker"] for p in book["pending"]]}
    prices = download_bars(tickers, day)
    updated, changed = process_day(config, state, day, prices,
                                    previous_session=previous,
                                    first_after_signal=first,
                                    week_end=week_end)
    if changed:
        write(output, updated)
    return {"status": "daily_recorded", "session": day,
            "week_end": week_end, "changed": changed}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["daily", "signal"], required=True)
    p.add_argument("--config", default="weekly_ml/config.json")
    p.add_argument("--forecast-dir", default="weekly_ml_state/forecasts")
    p.add_argument("--output", default="weekly_ml_daily_state/ledger.json")
    args = p.parse_args()
    try:
        result = run(args.config, args.forecast_dir, args.output, args.phase)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print("Weekly ML daily error: " + repr(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
