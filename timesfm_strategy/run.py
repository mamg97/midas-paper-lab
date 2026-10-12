"""TimesFM 2.5 weekly signals and daily EUR paper ledger, no broker connection.

Only causally observed post-close data can be used. No replays/backfills.
All equity transactions are in USD, translated to EUR:
next-open uses *previous XNYS session's observed FX close* as a causal proxy;
daily closes use current observed FX close (USD per EUR).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAMPAIGN = "timesfm_2p5_eur_paper"
ENGINE = "timesfm_2p5_weekly_eur_v1"
ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        json.dump(value, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def calendar(now=None):
    import pandas_market_calendars as calendars
    import pandas as pd
    now = now or datetime.now(timezone.utc)
    schedule = calendars.get_calendar("XNYS").schedule(
        start_date=(now - timedelta(days=22)).date(),
        end_date=(now + timedelta(days=12)).date())
    eligible = [i for i, (_, x) in enumerate(schedule.iterrows())
                if now >= x["market_close"].to_pydatetime() + timedelta(minutes=90)]
    if not eligible:
        return None
    idx = eligible[-1]
    if idx < 1 or idx + 1 >= len(schedule):
        raise ValueError("XNYS calendar boundary missing")
    next_open = schedule.iloc[idx + 1]["market_open"].to_pydatetime()
    if now >= next_open:
        raise ValueError("Next session already open: refuse hindsight")
    current = str(schedule.index[idx].date())
    previous = str(schedule.index[idx - 1].date())
    next_session = str(schedule.index[idx + 1].date())
    week_end = (schedule.index[idx].to_period("W-FRI") !=
                schedule.index[idx + 1].to_period("W-FRI"))
    return current, previous, next_session, bool(week_end)


def _series(raw, ticker):
    import pandas as pd
    if raw is None or raw.empty:
        raise ValueError("Vendor returned empty frame")
    if isinstance(raw.columns, pd.MultiIndex):
        if ticker not in raw.columns.get_level_values(0):
            raise ValueError("Vendor ticker missing: " + ticker)
        frame = raw[ticker].copy()
    else:
        frame = raw.copy()
    if frame.empty:
        raise ValueError("Vendor ticker empty: " + ticker)
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame


def _download(tickers, start, end):
    import yfinance as yf
    raw = yf.download(sorted(set(tickers)), start=start, end=end, interval="1d",
                      auto_adjust=False, actions=True, group_by="ticker",
                      threads=False, progress=False)
    return {ticker: _series(raw, ticker) for ticker in tickers}


def _last_row(frame, day, ticker):
    current = frame.loc[frame.index.strftime("%Y-%m-%d") == day]
    if len(current) != 1:
        raise ValueError("Missing exact dated OHLC: " + ticker + " " + day)
    return current.iloc[0]


def _positive(value, desc):
    n = float(value)
    if not math.isfinite(n) or n <= 0:
        raise ValueError("Invalid positive value " + desc)
    return n


def _config(config):
    p = config["execution"]
    if config["currency"] != "EUR" or config["initial_capital"] != 100000:
        raise ValueError("EUR 100k frozen campaign only")
    if config["model"]["horizon_sessions"] != 5:
        raise ValueError("Frozen five-session prediction horizon")
    if not 0 < p["capital_fraction"] <= 1 or p["max_weight"] * p["max_positions"] > 1:
        raise ValueError("Invalid risk exposure")
    if config["model"]["model_id"] != "google/timesfm-2.5-200m-pytorch":
        raise ValueError("Unexpected checkpoint")
    if len(config["tickers"]) != len(set(config["tickers"])):
        raise ValueError("Duplicate universe")


def _check(state, config):
    if (state.get("schema_version") != 1 or state.get("engine") != ENGINE
            or state.get("config_hash") != digest(config)
            or state.get("currency") != "EUR" or set(state.get("books", {})) != {"timesfm", "benchmark_spy"}):
        raise ValueError("Foreign or corrupted TimesFM ledger")
    if not state["equity"] or state["equity"][-1]["date"] != state["last_session"]:
        raise ValueError("TimesFM ledger dates not aligned")


def _book(capital, pending):
    return {"cash": capital, "nav": capital, "positions": {}, "pending": pending,
            "trades": [], "events": [], "equity": []}


def initialize(config, date, selected, forecasts):
    _config(config)
    capital = float(config["initial_capital"])
    result = {
        "schema_version": 1, "strategy_id": CAMPAIGN, "engine": ENGINE,
        "config_hash": digest(config), "currency": "EUR", "initial_capital": capital,
        "first_session": date, "last_session": date, "last_signal_session": date,
        "fx_method": "previous_XNYS_session_EURUSD_close_at_open; current_EURUSD_close_at_mark",
        "signals": [{"date": date, "selected": selected, "forecasts": forecasts}],
        "books": {
            "timesfm": _book(capital, selected),
            "benchmark_spy": _book(capital, [{"ticker": config["benchmark"], "signal_date": date}]),
        },
        "equity": [{"date": date, "nav": capital}],
    }
    for book in result["books"].values():
        book["equity"].append({"date": date, "nav": capital})
    return result


def record_signal(state, config, date, selected, forecasts):
    _check(state, config)
    if date <= state["last_signal_session"]:
        return copy.deepcopy(state), False
    if date != state["last_session"]:
        raise ValueError("A daily NAV is missing before new weekly signal")
    if state["books"]["timesfm"]["positions"] or state["books"]["timesfm"]["pending"]:
        raise ValueError("Previous TimesFM portfolio has not settled")
    new = copy.deepcopy(state)
    new["last_signal_session"] = date
    new["books"]["timesfm"]["pending"] = selected
    new["books"]["timesfm"]["events"].append({"date": date, "event": "signal", "count": len(selected)})
    new["signals"].append({"date": date, "selected": selected, "forecasts": forecasts})
    return new, True


def _qty(budget, price, policy):
    scale = 10 ** int(policy["share_precision"])
    qty = math.floor((budget / (price * (1 + policy["commission"]))) * scale) / scale
    if qty * price < policy["min_notional_eur"]:
        return 0.0
    return qty


def process_day(state, config, date, previous, bars, *, fx_entry, fx_mark, week_end):
    """Deterministic state transition; all USD prices and FX must be observed externally."""
    _check(state, config)
    if date <= state["last_session"]:
        return copy.deepcopy(state), False
    if previous != state["last_session"]:
        raise ValueError("Missed market session: never synthesize fills")
    _positive(fx_entry, "previous FX close")
    _positive(fx_mark, "current FX close")
    policy = config["execution"]
    new = copy.deepcopy(state)
    first_after_signal = (state["last_signal_session"] == previous)
    for name, book in new["books"].items():
        pending = list(book["pending"])
        if pending and not first_after_signal:
            raise ValueError("Paper buy signal missed next opening")
        # Apply corporate actions only to previously held shares; new buyers do not
        # receive a dividend on the entry date's ex-dividend event.
        for ticker, position in book["positions"].items():
            row = bars[ticker]
            split = float(row.get("split", 0))
            if split:
                _positive(split, "split ratio")
                position["shares"] *= split
                book["events"].append({"date": date, "ticker": ticker,
                                       "event": "split", "ratio": split})
            dividend = float(row.get("dividend", 0))
            if dividend:
                value = dividend * position["shares"] / fx_mark
                book["cash"] += value
                position["dividends_eur"] += value
                book["events"].append({"date": date, "ticker": ticker,
                                       "event": "dividend", "eur": value})
        if pending:
            total_fraction = policy["capital_fraction"]
            budget = min(float(book["nav"]) * total_fraction / len(pending),
                         float(book["nav"]) * (total_fraction if name == "benchmark_spy"
                                               else policy["max_weight"]))
            for order in pending:
                ticker = order["ticker"]
                open_usd = _positive(bars[ticker]["open"], ticker + " open")
                open_eur = (open_usd / fx_entry) * (1 + policy["slippage"])
                qty = _qty(budget, open_eur, policy)
                if qty <= 0:
                    book["events"].append({"date": date, "ticker": ticker,
                                           "event": "unfilled_below_min_notional"})
                    continue
                cost = open_eur * qty * (1 + policy["commission"])
                if cost > book["cash"] + 1e-6:
                    raise ValueError("Paper cash exceeded")
                if ticker in book["positions"]:
                    raise ValueError("Duplicate paper position")
                book["positions"][ticker] = {
                    "shares": qty, "entry_date": date, "signal_date": order["signal_date"],
                    "entry_price_eur": open_eur, "cost_eur": cost,
                    "dividends_eur": 0.0, "entry_fx": fx_entry
                }
                book["cash"] -= cost
                book["events"].append({"date": date, "ticker": ticker, "event": "buy",
                                       "shares": qty, "price_eur": open_eur, "fx": fx_entry})
            book["pending"] = []
        marks = {ticker: _positive(bars[ticker]["close"], ticker + " close") / fx_mark
                 for ticker in book["positions"]}
        if week_end and name == "timesfm":
            for ticker, position in list(book["positions"].items()):
                exit_price = marks[ticker] * (1 - policy["slippage"])
                proceeds = exit_price * position["shares"] * (1 - policy["commission"])
                book["cash"] += proceeds
                net_pnl = proceeds + position["dividends_eur"] - position["cost_eur"]
                book["trades"].append({
                    "ticker": ticker, "entry_date": position["entry_date"],
                    "exit_date": date, "signal_date": position["signal_date"],
                    "shares_at_exit": position["shares"], "buy_cost_eur": position["cost_eur"],
                    "sell_proceeds_eur": proceeds, "dividends_eur": position["dividends_eur"],
                    "net_pnl_eur": net_pnl
                })
                book["events"].append({"date": date, "ticker": ticker,
                                       "event": "sell", "price_eur": exit_price})
            book["positions"] = {}
        book["nav"] = book["cash"] + sum(pos["shares"] * marks[ticker]
                                          for ticker, pos in book["positions"].items())
        if not math.isfinite(book["nav"]) or book["nav"] < 0:
            raise ValueError("Invalid EUR NAV")
        book["equity"].append({"date": date, "nav": book["nav"]})
    new["last_session"] = date
    new["equity"].append({"date": date, "nav": new["books"]["timesfm"]["nav"]})
    return new, True


def _market_frame(config, date, *, signal):
    start = (datetime.fromisoformat(date) - timedelta(days=1200 if signal else 8)).date().isoformat()
    end = (datetime.fromisoformat(date) + timedelta(days=1)).date().isoformat()
    tickers = (config["tickers"] + [config["benchmark"]]) if signal else []
    return _download(tickers, start, end)


def get_forecasts(config, day):
    import numpy as np
    import timesfm
    panel = _market_frame(config, day, signal=True)
    spy = panel[config["benchmark"]]
    spy_row = _last_row(spy, day, config["benchmark"])
    prices_spy = spy["Adj Close"].dropna().astype(float).to_numpy()
    if len(prices_spy) < config["execution"]["market_sma_days"]:
        raise ValueError("SPY market regime cannot be computed")
    regime_on = float(spy_row["Adj Close"]) >= float(
        prices_spy[-config["execution"]["market_sma_days"]:].mean())
    tickers, arrays, vols = [], [], {}
    for ticker in config["tickers"]:
        try:
            frame = panel[ticker]
            row = _last_row(frame, day, ticker)
            close = frame["Adj Close"].dropna().astype(float).to_numpy()
            if len(close) < config["model"]["min_history_days"] or not np.all(np.isfinite(close[-512:])):
                continue
            ret = np.diff(np.log(close[-22:]))
            vol = float(np.std(ret, ddof=1) * np.sqrt(252))
            if not math.isfinite(vol):
                continue
            tickers.append(ticker)
            arrays.append(close[-config["model"]["context_days"]:].astype(np.float32))
            vols[ticker] = vol
        except (ValueError, KeyError, TypeError):
            continue
    if len(tickers) < 18:
        raise ValueError("Insufficient complete dated candidate series")
    # Deliberate 2.5: 3.0 weights are non-commercial and not production-licensed.
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        config["model"]["model_id"], revision=config["model"]["revision"],
        force_download=False)
    model.compile(timesfm.ForecastConfig(
        max_context=config["model"]["context_days"],
        max_horizon=config["model"]["horizon_sessions"],
        per_core_batch_size=4, normalize_inputs=True,
        use_continuous_quantile_head=False, force_flip_invariance=True,
        infer_is_positive=True))
    point, _ = model.forecast(horizon=config["model"]["horizon_sessions"], inputs=arrays)
    point = np.asarray(point)
    if point.shape != (len(tickers), config["model"]["horizon_sessions"]):
        raise ValueError("TimesFM returned unexpected forecast dimensions")
    ranked = []
    for i, ticker in enumerate(tickers):
        expected = float(point[i, -1] / arrays[i][-1] - 1)
        if not math.isfinite(expected):
            continue
        risk = vols[ticker] * math.sqrt(5 / 252)
        score = expected - config["execution"]["risk_penalty"] * risk
        ranked.append({"ticker": ticker, "predicted_return": expected,
                       "risk_5d": risk, "score": score})
    ranked.sort(key=lambda x: (-x["score"], x["ticker"]))
    selected = ([{"ticker": x["ticker"], "signal_date": day,
                  "predicted_return": x["predicted_return"], "score": x["score"]}
                 for x in ranked
                 if x["predicted_return"] >= config["execution"]["min_forecast_return"]
                 and x["score"] > 2 * (config["execution"]["commission"] +
                                       config["execution"]["slippage"])][
                     :config["execution"]["max_positions"]]
                if regime_on else [])
    return selected, {"model": config["model"]["model_id"],
                      "revision": config["model"]["revision"],
                      "horizon": config["model"]["horizon_sessions"],
                      "market_regime_on": bool(regime_on), "scored": ranked,
                      "candidate_count": len(tickers)}


def _daily_bars(config, state, day, previous):
    needed = sorted({o["ticker"] for b in state["books"].values()
                     for o in b["pending"]} | {t for b in state["books"].values()
                                                for t in b["positions"]})
    start = (datetime.fromisoformat(previous) - timedelta(days=4)).date().isoformat()
    end = (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()
    fx = _download([config["fx_ticker"]], start, end)[config["fx_ticker"]]
    fx_entry = _positive(_last_row(fx, previous, config["fx_ticker"])["Close"], "FX entry")
    fx_mark = _positive(_last_row(fx, day, config["fx_ticker"])["Close"], "FX close")
    bars = {}
    if needed:
        stocks = _download(needed, start, end)
        for ticker in needed:
            r = _last_row(stocks[ticker], day, ticker)
            bars[ticker] = {
                "open": _positive(r["Open"], ticker + " open"),
                "close": _positive(r["Close"], ticker + " close"),
                "dividend": float(r.get("Dividends", 0)),
                "split": float(r.get("Stock Splits", 0))
            }
    return bars, fx_entry, fx_mark


def run(config_path, state_path, phase):
    config = read(config_path)
    _config(config)
    state_path = Path(state_path)
    state = read(state_path) if state_path.exists() else None
    when = calendar()
    if when is None:
        return {"status": "market_not_ready"}
    day, previous, next_session, week_end = when
    if state is not None:
        _check(state, config)
    if phase == "daily":
        if state is None:
            return {"status": "awaiting_first_signal"}
        if day <= state["last_session"]:
            return {"status": "already_recorded", "session": day}
        bars, entry_fx, close_fx = _daily_bars(config, state, day, previous)
        updated, changed = process_day(state, config, day, previous, bars,
                                       fx_entry=entry_fx, fx_mark=close_fx,
                                       week_end=week_end)
        if changed:
            atomic_write(state_path, updated)
        return {"status": "daily_recorded", "session": day, "week_end": week_end}
    if phase != "signal":
        raise ValueError("Unknown phase")
    if not week_end:
        return {"status": "not_last_market_session_of_week", "session": day}
    if state is not None:
        if state["last_signal_session"] >= day:
            return {"status": "already_signaled", "session": day}
        if state["last_session"] != day:
            raise ValueError("Daily ledger not caught up: refuse forecast")
    selected, diagnostic = get_forecasts(config, day)
    result = (initialize(config, day, selected, diagnostic) if state is None
              else record_signal(state, config, day, selected, diagnostic)[0])
    atomic_write(state_path, result)
    return {"status": "signal_frozen", "session": day,
            "selected": len(selected), "currency": "EUR", "capital": 100000}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["daily", "signal", "check"], required=True)
    p.add_argument("--config", default=str(ROOT / "timesfm_strategy/config.json"))
    p.add_argument("--state", default=str(ROOT / "timesfm_state/ledger.json"))
    args = p.parse_args()
    try:
        config = read(args.config)
        _config(config)
        if args.phase == "check":
            print(json.dumps({"status": "valid_config", "currency": "EUR",
                              "capital": config["initial_capital"]}))
            return 0
        print(json.dumps(run(args.config, args.state, args.phase), ensure_ascii=False))
        return 0
    except Exception as err:
        print("TIMESFM PAPER ERROR: " + repr(err))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
