"""Independent TimesFM 2.5 one-session EUR paper campaign.

Forecast known only after the preceding NYSE close. Trades can be recorded
only after the next closed session, at observed OPEN -> CLOSE prices.
No backfill and no real broker, and no inheritance from weekly campaign.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import run as core

ROOT = Path(__file__).resolve().parents[1]
ENGINE = "timesfm_2p5_daily_eur_v1"
CAMPAIGN = "timesfm_2p5_daily_eur_paper"
BOOKS = ("timesfm_daily", "benchmark_spy")


def verify(config):
    if (config.get("name") != "MIDAS_timesfm_2p5_eur_daily_2026"
            or config.get("currency") != "EUR"
            or config.get("initial_capital") != 100000
            or config.get("model", {}).get("horizon_sessions") != 1):
        raise ValueError("Frozen EUR 100k one-session campaign expected")
    if config.get("model", {}).get("model_id") != "google/timesfm-2.5-200m-pytorch":
        raise ValueError("Wrong TimesFM model")
    p = config["execution"]
    if not (0 < p["capital_fraction"] <= 1
            and p["max_positions"] >= 1
            and 0 < p["max_weight"] <= 1
            and p["max_positions"] * p["max_weight"] <= 1):
        raise ValueError("Risk policy invalid")


def check(state, config):
    if (state.get("engine") != ENGINE
            or state.get("strategy_id") != CAMPAIGN
            or state.get("config_hash") != core.digest(config)
            or state.get("currency") != "EUR"
            or set(state.get("books", {})) != set(BOOKS)
            or not state.get("equity")
            or state["equity"][-1]["date"] != state["last_session"]):
        raise ValueError("Invalid or foreign daily TimesFM ledger")
    for book in state["books"].values():
        if not book.get("equity") or book["equity"][-1]["date"] != state["last_session"]:
            raise ValueError("Book has no matching EUR close")


def initialize(config, day, selected, diagnostics):
    verify(config)
    capital = float(config["initial_capital"])
    orders = [{"ticker": x["ticker"], "signal_date": day,
               "predicted_return": x.get("predicted_return"), "score": x.get("score")}
              for x in selected]
    result = {
        "schema_version": 1, "strategy_id": CAMPAIGN, "engine": ENGINE,
        "config_hash": core.digest(config), "currency": "EUR",
        "initial_capital": capital, "first_session": day, "last_session": day,
        "last_signal_session": day,
        "fx_method": "previous_XNYS_session_EURUSD_close_at_open; current_EURUSD_close_at_mark",
        "signal_history": [{"date": day, "selected": orders, "diagnostics": diagnostics}],
        "books": {
            "timesfm_daily": core._book(capital, orders),
            "benchmark_spy": core._book(capital, [{"ticker": config["benchmark"], "signal_date": day}]),
        },
        "equity": [{"date": day, "nav": capital}],
        "missing_signals": [],
    }
    for book in result["books"].values():
        book["equity"].append({"date": day, "nav": capital})
    return result


def process_session(state, config, date, previous, bars, *, fx_entry, fx_mark):
    """Atomic EUR settlement for one opened-and-now-closed market session."""
    check(state, config)
    if date <= state["last_session"]:
        return copy.deepcopy(state), False
    if previous != state["last_session"]:
        raise ValueError("Missed XNYS session: no retroactive fills")
    core._positive(fx_entry, "FX at entry")
    core._positive(fx_mark, "FX at close")
    p = config["execution"]
    result = copy.deepcopy(state)
    for book_name, book in result["books"].items():
        for ticker, pos in book["positions"].items():
            row = bars[ticker]
            split = float(row.get("split", 0))
            if split:
                core._positive(split, "split")
                pos["shares"] *= split
                book["events"].append({"date": date, "type": "split", "ticker": ticker, "ratio": split})
            dividend = float(row.get("dividend", 0))
            if dividend:
                gross = pos["shares"] * dividend / fx_mark
                book["cash"] += gross
                pos["dividends_eur"] += gross
                book["events"].append({"date": date, "type": "dividend", "ticker": ticker, "eur": gross})
        pending = book["pending"]
        if pending:
            if not all(x["signal_date"] == previous for x in pending):
                raise ValueError("Pending orders are not next-open orders")
            budget = min(float(book["nav"]) * p["capital_fraction"] / len(pending),
                         float(book["nav"]) * (p["capital_fraction"]
                                                if book_name == "benchmark_spy" else p["max_weight"]))
            for order in pending:
                ticker = order["ticker"]
                entry = core._positive(bars[ticker]["open"], "open " + ticker) / fx_entry
                entry *= 1 + p["slippage"]
                quantity = core._qty(budget, entry, p)
                if quantity <= 0:
                    book["events"].append({"date": date, "type": "unfilled", "ticker": ticker})
                    continue
                cost = entry * quantity * (1 + p["commission"])
                if cost > book["cash"] + 1e-7 or ticker in book["positions"]:
                    raise ValueError("Overspend or duplicate position")
                book["cash"] -= cost
                book["positions"][ticker] = {
                    "shares": quantity, "entry_date": date, "signal_date": previous,
                    "entry_price_eur": entry, "cost_eur": cost, "dividends_eur": 0.0,
                    "fx_at_entry": fx_entry,
                }
                book["events"].append({"date": date, "type": "buy", "ticker": ticker,
                                       "shares": quantity, "entry_eur": entry})
            book["pending"] = []
        marked = {ticker: core._positive(bars[ticker]["close"], "close " + ticker) / fx_mark
                  for ticker in book["positions"]}
        # Intraday: exit at the same day's observed close, never hold overnight.
        if book_name == "timesfm_daily":
            for ticker, pos in list(book["positions"].items()):
                sale_price = marked[ticker] * (1 - p["slippage"])
                proceeds = pos["shares"] * sale_price * (1 - p["commission"])
                book["cash"] += proceeds
                book["trades"].append({
                    "ticker": ticker, "signal_date": pos["signal_date"],
                    "entry_date": date, "exit_date": date,
                    "shares": pos["shares"], "entry_cost_eur": pos["cost_eur"],
                    "sale_eur": proceeds, "net_pnl_eur": proceeds - pos["cost_eur"] + pos["dividends_eur"],
                })
                book["events"].append({"date": date, "type": "sell", "ticker": ticker})
            book["positions"] = {}
        book["nav"] = book["cash"] + sum(pos["shares"] * marked[ticker] for ticker, pos in book["positions"].items())
        if not math.isfinite(book["nav"]) or book["nav"] < 0:
            raise ValueError("Invalid EUR NAV")
        book["equity"].append({"date": date, "nav": book["nav"]})
    result["last_session"] = date
    result["equity"].append({"date": date, "nav": result["books"]["timesfm_daily"]["nav"]})
    return result, True


def freeze_signal(state, config, date, selected, diagnostics):
    check(state, config)
    if date < state["last_session"]:
        raise ValueError("Cannot create historical signal")
    if date == state["last_signal_session"]:
        return copy.deepcopy(state), False
    if date != state["last_session"]:
        raise ValueError("Cannot freeze signal without same-day EUR NAV")
    if state["books"]["timesfm_daily"]["positions"] or state["books"]["timesfm_daily"]["pending"]:
        raise ValueError("Daily book is not settled")
    updated = copy.deepcopy(state)
    updated["books"]["timesfm_daily"]["pending"] = [
        {"ticker": x["ticker"], "signal_date": date,
         "predicted_return": x.get("predicted_return"), "score": x.get("score")}
        for x in selected]
    updated["last_signal_session"] = date
    updated["signal_history"].append({"date": date, "selected": selected, "diagnostics": diagnostics})
    return updated, True


def run(config_path, state_path):
    config = core.read(config_path)
    verify(config)
    state_path = Path(state_path)
    state = core.read(state_path) if state_path.exists() else None
    moment = core.calendar()
    if moment is None:
        return {"status": "no_eligible_market_close", "changed": False}
    day, previous, _, _ = moment
    if state is not None:
        check(state, config)
        if day < state["last_session"]:
            raise ValueError("Current date precedes frozen ledger")
    if state is None:
        selected, diagnostics = core.get_forecasts(config, day)
        state = initialize(config, day, selected, diagnostics)
        core.atomic_write(state_path, state)
        return {"status": "first_daily_signal_frozen", "date": day, "selected": len(selected)}
    if day > state["last_session"]:
        if state["last_signal_session"] != state["last_session"]:
            # A prior forecast was not persisted. Record a missed decision,
            # but do not generate or invent it after its next open occurred.
            state = copy.deepcopy(state)
            state["missing_signals"].append(state["last_session"])
        bars, fx_entry, fx_mark = core._daily_bars(config, state, day, previous)
        state, changed = process_session(state, config, day, previous, bars,
                                         fx_entry=fx_entry, fx_mark=fx_mark)
        if changed:
            core.atomic_write(state_path, state)
    if state["last_signal_session"] == day:
        return {"status": "already_recorded", "date": day}
    # The settlement above is persisted BEFORE heavy model inference.
    # If inference fails, current NAV remains valid and same-session retry
    # is permitted while the next market has not yet opened.
    selected, diagnostics = core.get_forecasts(config, day)
    updated, changed = freeze_signal(state, config, day, selected, diagnostics)
    if changed:
        core.atomic_write(state_path, updated)
    return {"status": "daily_signal_frozen", "date": day, "selected": len(selected),
            "currency": "EUR", "initial_capital": 100000}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["check", "daily"], required=True)
    p.add_argument("--config", default=str(ROOT / "timesfm_strategy/config-daily.json"))
    p.add_argument("--state", default=str(ROOT / "timesfm_daily_state/ledger.json"))
    args = p.parse_args()
    try:
        if args.phase == "check":
            c = core.read(args.config)
            verify(c)
            print(json.dumps({"status": "valid", "capital": 100000,
                              "currency": "EUR", "horizon_sessions": 1}))
            return 0
        print(json.dumps(run(args.config, args.state), ensure_ascii=False))
        return 0
    except Exception as error:
        print("TIMESFM DAILY ERROR: " + repr(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
