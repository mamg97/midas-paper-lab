"""S&P 500 classic indicator campaign. Prospective next-open paper; no broker.

Eight reimplemented variants share all frozen 503 constituent symbols. Legacy
eight-stock histories remain separate and unchanged.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "paper_demo"))
from strategies import signal

spec = importlib.util.spec_from_file_location("timesfm_market_lib", ROOT / "timesfm_strategy/run.py")
market = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market)

ENGINE = "classic_sp500_next_open_v2"
BENCHMARK = "benchmark_spy"
CAMPAIGN = "classic_sp500_us_2026"


def verify_config(config):
    if (config.get("name") != "MIDAS_classic_SP500_forward_2026"
            or config.get("currency") != "USD"
            or config.get("initial_capital") != 100000
            or config.get("universe_file") != "weekly_ml/universe_sp500_2026-09-29.csv"):
        raise ValueError("Invalid common-universe forward classic campaign")
    universe = market.load_universe(config["universe_file"])
    if len(universe) != 503:
        raise ValueError("Expected frozen 503 constituents")
    p = config["execution"]
    if not (.85 <= p["minimum_eligible_coverage"] <= 1
            and 0 < p["max_positions"] <= 15
            and 0 < p["capital_fraction"] <= 1
            and 0 < p["max_weight"] <= 1):
        raise ValueError("Risk settings invalid")
    return universe


def new_book(capital):
    return {"cash": capital, "nav": capital, "positions": {}, "pending": {},
            "trades": [], "events": [], "equity": [], "signal_counts": []}


def validate_state(state, config):
    expected = set(config["strategies"]) | {BENCHMARK}
    if (state.get("engine") != ENGINE or state.get("config_hash") != market.digest(config)
            or state.get("currency") != "USD" or set(state.get("books", {})) != expected
            or not state.get("first_session") or not state.get("last_session")):
        raise ValueError("Foreign classic S&P 500 portfolio ledger")
    for book in state["books"].values():
        if not book["equity"] or book["equity"][-1]["date"] != state["last_session"]:
            raise ValueError("Book lacks observed latest NAV")


def rank_signals(config, panel, session):
    """One causal decision on each eligible constituent with a dated bar."""
    universe = verify_config(config)
    coverage = {t: "no_current_bar" for t in universe}
    eligible = {}
    for ticker in universe:
        frame = panel.get(ticker)
        if frame is None or len(frame) < 80:
            coverage[ticker] = "short_or_absent_history"
            continue
        try:
            market._last_row(frame, session, ticker)
        except ValueError:
            coverage[ticker] = "missing_current_close"
            continue
        eligible[ticker] = [
            {"date": str(idx.date()), "open": float(row["Open"]),
             "high": float(row["High"]), "low": float(row["Low"]),
             "close": float(row["Close"]), "volume": float(row["Volume"])}
            for idx, row in frame.tail(300).iterrows()]
        coverage[ticker] = "evaluated"
    needed = math.ceil(len(universe) * config["execution"]["minimum_eligible_coverage"])
    if len(eligible) < needed:
        raise ValueError(f"S&P500 insufficient dated data {len(eligible)}/{len(universe)}")
    orders = {}
    for name, strategy in config["strategies"].items():
        mode = strategy["kind"]
        ranked = []
        for ticker in universe:
            rows = eligible.get(ticker)
            if rows is None:
                continue
            status = signal(mode, rows, strategy.get("params") or {})
            if status == "hold":
                continue
            # Deterministic ex-ante priority among same-session buy signals.
            # For long strategies, 21-session momentum is a tie-breaker, not
            # an additional retroactively optimised prediction.
            momentum = rows[-1]["close"] / rows[-22]["close"] - 1
            ranked.append((ticker, status, float(momentum)))
        orders[name] = sorted(ranked, key=lambda x: (-x[2], x[0]))
    return orders, {"eligible": len(eligible), "total": len(universe),
                    "missing": {t: reason for t, reason in coverage.items() if reason != "evaluated"},
                    "ticker_coverage_pct": round(len(eligible) / len(universe) * 100, 3)}


def frozen_orders(config, name, signal_rows, positions, date):
    if name == BENCHMARK:
        return {"SPY": {"side": "buy", "signal_date": date}} if "SPY" not in positions else {}
    if name == "buy_hold_equal_weight":
        return {ticker: {"side": "buy", "signal_date": date}
                for ticker, action, _ in signal_rows if action == "buy" and ticker not in positions}
    pending = {ticker: {"side": "sell", "signal_date": date}
               for ticker, action, _ in signal_rows if action == "sell" and ticker in positions}
    slots = max(0, config["execution"]["max_positions"] - len(positions) + len(pending))
    entries = [ticker for ticker, action, _ in signal_rows
               if action == "buy" and ticker not in positions][:slots]
    for ticker in entries:
        pending[ticker] = {"side": "buy", "signal_date": date}
    return pending


def initialize(config, date, orders, diagnostic):
    verify_config(config)
    books = {}
    for name in [*config["strategies"], BENCHMARK]:
        book = new_book(float(config["initial_capital"]))
        book["pending"] = frozen_orders(config, name, orders.get(name, []), {}, date)
        book["equity"] = [{"date": date, "nav": book["nav"]}]
        book["signal_counts"].append({"date": date, "buys": sum(o["side"] == "buy" for o in book["pending"].values())})
        books[name] = book
    return {"schema_version": 1, "strategy_id": CAMPAIGN, "engine": ENGINE,
            "config_hash": market.digest(config), "currency": "USD",
            "initial_capital": config["initial_capital"],
            "first_session": date, "last_session": date,
            "coverage": [{"date": date, **diagnostic}],
            "books": books}


def _close_position(book, ticker, value, day, config, reason):
    pos = book["positions"].pop(ticker)
    price = market._positive(value, "sale") * (1 - config["execution"]["slippage"])
    shares = pos["shares"]
    fee = shares * price * config["execution"]["commission"]
    proceeds = shares * price - fee
    book["cash"] += proceeds
    book["trades"].append({"ticker": ticker, "entry_date": pos["entry_date"],
                           "exit_date": day, "entry_cost": pos["cost"], "proceeds": proceeds,
                           "dividends": pos["dividends"], "net_pnl": proceeds + pos["dividends"] - pos["cost"],
                           "reason": reason})
    book["events"].append({"date": day, "ticker": ticker, "type": "sell", "reason": reason})


def settle(config, state, day, previous, today):
    """Pure state transition; same dated OHLC for every paper event."""
    validate_state(state, config)
    if day <= state["last_session"]:
        return copy.deepcopy(state), False
    if previous != state["last_session"]:
        raise ValueError("Missing market session: never replay old opens")
    result = copy.deepcopy(state)
    p = config["execution"]
    for name, book in result["books"].items():
        for ticker, pos in list(book["positions"].items()):
            bar = today[ticker]
            split = float(bar.get("split", 0))
            if split:
                pos["shares"] *= market._positive(split, "split")
                if pos["stop"] is not None:
                    pos["stop"] /= split
                if pos["target"] is not None:
                    pos["target"] /= split
                book["events"].append({"date": day, "ticker": ticker, "type": "split", "ratio": split})
            dividend = float(bar.get("dividend", 0))
            if dividend:
                amount = pos["shares"] * dividend
                book["cash"] += amount
                pos["dividends"] += amount
        sells = sorted(t for t, order in book["pending"].items() if order["side"] == "sell")
        for ticker in sells:
            if ticker not in book["positions"]:
                raise ValueError("Orphan sell signal")
            _close_position(book, ticker, today[ticker]["open"], day, config, "signal_next_open")
        buy_list = sorted(t for t, order in book["pending"].items() if order["side"] == "buy")
        nav_at_open = book["cash"] + sum(pos["shares"] * today[t]["open"] for t, pos in book["positions"].items())
        if buy_list:
            if name == "buy_hold_equal_weight":
                budget = nav_at_open * p["capital_fraction"] / 503
            else:
                budget = min(nav_at_open * p["capital_fraction"] / len(buy_list),
                             nav_at_open * (p["capital_fraction"] if name == BENCHMARK else p["max_weight"]))
            for ticker in buy_list:
                if ticker in book["positions"]:
                    continue
                price = market._positive(today[ticker]["open"], "buy open") * (1 + p["slippage"])
                scale = 10 ** p["fractional_precision"]
                shares = math.floor(budget / (price * (1 + p["commission"])) * scale) / scale
                cost = shares * price * (1 + p["commission"])
                if cost < p["minimum_notional"] or cost > book["cash"] + 1e-7:
                    book["events"].append({"date": day, "ticker": ticker, "type": "unfilled"})
                    continue
                spec = config["strategies"].get(name, {})
                book["positions"][ticker] = {
                    "shares": shares, "entry_date": day, "entry_price": price,
                    "cost": cost, "dividends": 0.0,
                    "stop": price * (1 - spec["stop_loss"]) if spec.get("stop_loss") else None,
                    "target": price * (1 + spec["take_profit"]) if spec.get("take_profit") else None}
                book["cash"] -= cost
                book["events"].append({"date": day, "ticker": ticker, "type": "buy", "shares": shares})
        book["pending"] = {}
        # Conservative candle execution: if stop and target both occur, stop wins.
        for ticker, pos in list(book["positions"].items()):
            bar = today[ticker]
            if pos["stop"] is not None and bar["low"] <= pos["stop"]:
                price = min(bar["open"], pos["stop"])
                _close_position(book, ticker, price, day, config, "stop")
            elif pos["target"] is not None and bar["high"] >= pos["target"]:
                price = max(bar["open"], pos["target"])
                _close_position(book, ticker, price, day, config, "target")
        book["nav"] = book["cash"] + sum(pos["shares"] * market._positive(today[t]["close"], "mark")
                                           for t, pos in book["positions"].items())
        if not math.isfinite(book["nav"]) or book["nav"] < 0:
            raise ValueError("Invalid classic USD NAV")
        book["equity"].append({"date": day, "nav": book["nav"]})
    result["last_session"] = day
    return result, True


def freeze(config, state, day, decisions, coverage):
    validate_state(state, config)
    if state["last_session"] != day:
        raise ValueError("Current market close not marked")
    new = copy.deepcopy(state)
    for name, book in new["books"].items():
        book["pending"] = frozen_orders(config, name, decisions.get(name, []), book["positions"], day)
        book["signal_counts"].append({"date": day, "buys": sum(o["side"] == "buy" for o in book["pending"].values())})
    new["coverage"].append({"date": day, **coverage})
    return new


def fetch_live(config, session, previous, symbols):
    start = (datetime.fromisoformat(session) - timedelta(days=config["execution"]["history_calendar_days"])).date().isoformat()
    end = (datetime.fromisoformat(session) + timedelta(days=1)).date().isoformat()
    frames = market._download(symbols + [config["benchmark_ticker"]], start, end, allow_missing=True)
    today = {}
    for ticker, frame in frames.items():
        try:
            row = market._last_row(frame, session, ticker)
            today[ticker] = {"open": market._positive(row["Open"], "open"),
                             "high": market._positive(row["High"], "high"),
                             "low": market._positive(row["Low"], "low"),
                             "close": market._positive(row["Close"], "close"),
                             "split": float(row.get("Stock Splits", 0)),
                             "dividend": float(row.get("Dividends", 0))}
        except ValueError:
            continue
    return frames, today


def run(config_path, state_path):
    config = market.read(config_path)
    symbols = verify_config(config)
    state_path = Path(state_path)
    state = market.read(state_path) if state_path.exists() else None
    cal = market.calendar()
    if cal is None:
        return {"status": "market_not_closed"}
    day, previous, _, _ = cal
    if state is not None:
        validate_state(state, config)
        if day <= state["last_session"]:
            return {"status": "already_recorded", "session": day}
        if previous != state["last_session"]:
            raise ValueError("Forward S&P500 classic ledger has a missing market session")
    frames, today = fetch_live(config, day, previous, symbols)
    decisions, coverage = rank_signals(config, frames, day)
    if state is None:
        fresh = initialize(config, day, decisions, coverage)
        market.atomic_write(state_path, fresh)
        return {"status": "first_signal_frozen", "date": day, "eligible": coverage["eligible"],
                "universe": coverage["total"]}
    needed = {ticker for b in state["books"].values()
              for ticker in set(b["positions"]) | set(b["pending"])}
    if not needed <= set(today):
        raise ValueError("Missing dated bar for held position or pending order: " +
                         ",".join(sorted(needed - set(today))))
    updated, changed = settle(config, state, day, previous, today)
    if changed:
        updated = freeze(config, updated, day, decisions, coverage)
        market.atomic_write(state_path, updated)
    return {"status": "paper_recorded", "date": day, "eligible": coverage["eligible"],
            "universe": coverage["total"], "models": len(config["strategies"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["check", "daily"], default="check")
    parser.add_argument("--config", default=str(ROOT / "classic_sp500/config.json"))
    parser.add_argument("--state", default=str(ROOT / "classic_sp500_state/ledger.json"))
    args = parser.parse_args()
    try:
        if args.phase == "check":
            config = market.read(args.config)
            symbols = verify_config(config)
            print(json.dumps({"status": "config_valid", "universe": len(symbols)}))
            return 0
        print(json.dumps(run(args.config, args.state), ensure_ascii=False))
        return 0
    except Exception as exc:
        print("CLASSIC SP500 ERROR: " + repr(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
