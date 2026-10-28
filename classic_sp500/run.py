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
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "paper_demo"))
from market_data.consume import overlay as overlay_common_ohlc
from strategies import signal

spec = importlib.util.spec_from_file_location("timesfm_market_lib", ROOT / "timesfm_strategy/run.py")
market = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market)

ENGINE = "classic_sp500_next_open_v2"
BENCHMARK = "benchmark_spy"
CAMPAIGN = "classic_sp500_us_2026"

# Public issuer-confirmed *same security* ticker transition, not a portfolio
# substitution. SEC 2026-10-06 8-K: https://www.sec.gov/Archives/edgar/data/
# 2041610/000110465926113913/tm2626659d7_8k.htm
# Skydance Class B moved Nasdaq->NYSE, ticker PSKY->SKYD effective Oct 6.
# Only the market-data identity changes; books preserve their frozen IDs,
# cost basis, positions, stop/target and prior equity unchanged.
VERIFIED_TICKER_RENAMES = {"PSKY": ("SKYD", "2026-10-06")}


def verified_price_symbol(ticker, session):
    change = VERIFIED_TICKER_RENAMES.get(ticker)
    return change[0] if change and session >= change[1] else None



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
        if not book["equity"]:
            raise ValueError("Book lacks observed latest NAV")
        latest = book["equity"][-1]["date"]
        paused = book.get("paused_missing_quotes")
        if paused:
            if (latest >= state["last_session"]
                    or paused.get("last_valued_session") != latest
                    or not paused.get("since")
                    or not paused.get("missing_tickers")):
                raise ValueError("Invalid unpriced book quarantine")
        elif latest != state["last_session"]:
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
            # The dated close alone does not make the instrument tradeable:
            # a missing/zero Open or invalid OHLC must not freeze new BUYs.
            # Keep such symbols in the frozen 503 denominator and record
            # them explicitly as unavailable, without substituting prices.
            market._last_row(frame, session, ticker)
        except (ValueError, TypeError, KeyError):
            coverage[ticker] = "missing_current_close"
            continue
        try:
            _dated_bar(frame, session, ticker)
        except (ValueError, TypeError, KeyError, OverflowError):
            coverage[ticker] = "invalid_current_ohlc"
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


def settle(config, state, day, previous, today, *, allow_partial=False):
    """Pure paper transition. Isolate unpriced books, never invent a daily NAV.

    The strict default preserves backwards-compatibility for historical gap
    reconciliation. Current live schedules may quarantine a single affected
    book while the other eight books receive independently verified marks.
    """
    validate_state(state, config)
    if day <= state["last_session"]:
        return copy.deepcopy(state), False
    if previous != state["last_session"]:
        raise ValueError("Missing market session: never replay old opens")
    # Existing holdings or exit signals require a real dated bar. Missing
    # prices for new, unfilled BUY requests must not prevent other portfolios
    # from proceeding, but an existing exposure is never marked with stale data.
    required = {ticker for book in state["books"].values()
                for ticker in set(book["positions"]) |
                {t for t, order in book["pending"].items() if order["side"] == "sell"}}
    if not allow_partial and not required <= set(today):
        raise ValueError("Missing dated bar for held position or pending sell: " +
                         ",".join(sorted(required - set(today))))
    result = copy.deepcopy(state)
    p = config["execution"]
    for name, book in result["books"].items():
        if allow_partial:
            # A previously quarantined book cannot skip an observed session.
            # It stays at its LAST VERIFIED NAV until its dated session gap is
            # independently reconciled. Never silently resume at a later close.
            if book.get("paused_missing_quotes"):
                continue
            mandatory = set(book["positions"]) | {
                t for t, order in book["pending"].items() if order["side"] == "sell"
            }
            missing = sorted(mandatory - set(today))
            if missing:
                book["paused_missing_quotes"] = {
                    "since": day,
                    "last_valued_session": book["equity"][-1]["date"],
                    "missing_tickers": missing,
                    "reason": "required same-session bar unavailable",
                }
                book["events"].append({
                    "date": day, "type": "book_quarantined_missing_held_bar",
                    "missing_tickers": missing,
                })
                continue
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
                if ticker not in today:
                    # No same-session OHLC => no evidence of an executable fill.
                    # Keep the remaining buy budgets unchanged; never redistribute
                    # unavailable constituents' cash or use a later day's price.
                    book["events"].append({
                        "date": day, "ticker": ticker,
                        "type": "unfilled_missing_dated_bar",
                        "reason": "required same-session OHLC unavailable",
                    })
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
        if book.get("paused_missing_quotes"):
            # No next-session orders from a session we could not value.
            continue
        book["pending"] = frozen_orders(config, name, decisions.get(name, []), book["positions"], day)
        book["signal_counts"].append({"date": day, "buys": sum(o["side"] == "buy" for o in book["pending"].values())})
    new["coverage"].append({"date": day, **coverage})
    return new


def recover_flat_gap(config, state, day, previous, decisions, coverage):
    """Resume an interrupted flat campaign without backdating nonexistent fills.

    Expire the 12th's unfilled orders; generate new decisions at the last
    observed close. Missing sessions are metadata, NEVER synthetic NAV rows.
    An invested portfolio must still fail closed: no prices may be inferred.
    """
    validate_state(state, config)
    if any(book["positions"] for book in state["books"].values()):
        raise ValueError("Missed market session with open positions: manual review required")
    import pandas_market_calendars as calendars
    sessions = calendars.get_calendar("XNYS").valid_days(
        start_date=state["last_session"], end_date=day)
    observed = [str(session.date()) for session in sessions]
    missed = observed[1:-1]
    if (len(observed) < 3 or observed[0] != state["last_session"]
            or observed[-1] != day or missed[-1] != previous):
        raise ValueError("Cannot verify exact missed XNYS market sessions")

    result = copy.deepcopy(state)
    expired = 0
    for book in result["books"].values():
        if book["positions"] or book["trades"]:
            raise ValueError("Flat-gap recovery cannot rewrite executed trading history")
        count = len(book["pending"])
        expired += count
        book["events"].append({
            "date": day, "type": "missed_session_unfilled",
            "missed_sessions": missed, "expired_pending_orders": count,
            "reason": "past opening fills never executed or inferred"
        })
        book["pending"] = {}
        # Portfolio was fully in cash: only a real observed day gets a NAV.
        if not math.isclose(book["nav"], book["cash"], rel_tol=0, abs_tol=1e-7):
            raise ValueError("Flat-gap recovery requires cash-only NAV")
        book["equity"].append({"date": day, "nav": book["cash"]})
    result["last_session"] = day
    result.setdefault("missed_sessions", []).extend(missed)
    result = freeze(config, result, day, decisions, coverage)
    return result, missed, expired


def market_sessions_after(last_session, day, previous, *, max_reconcile=3):
    """Verify every XNYS date before considering a delayed paper settlement."""
    import pandas_market_calendars as calendars
    sessions = calendars.get_calendar("XNYS").valid_days(
        start_date=last_session, end_date=day)
    observed = [str(session.date()) for session in sessions]
    if (len(observed) < 3 or observed[0] != last_session
            or observed[-1] != day or observed[-2] != previous):
        raise ValueError("Cannot verify exact missed XNYS market sessions")
    if len(observed) - 1 > max_reconcile:
        raise ValueError("Invested gap exceeds bounded reconciliation window")
    return observed


def required_live_quotes(state):
    """Only held exposures and pending sells require a valid mark to proceed."""
    return {ticker for book in state["books"].values()
            for ticker in set(book["positions"]) |
            {ticker for ticker, order in book["pending"].items()
             if order["side"] == "sell"}}


def reconcile_invested_gap(config, state, day, previous, symbols):
    """Delayed, deterministic paper settlement on EXACT historical XNYS bars.

    This is a disclosed late calculation from previously frozen strategy rules;
    it is not a claim that GitHub Actions executed successfully on those dates.
    Each session still requires real dated OHLC and sufficient universe
    coverage. A missing HELD symbol quarantines only its exposed paper book;
    unaffected books advance with fully observed marks. The complete transition
    is persisted atomically, never as a partially written JSON file.
    """
    validate_state(state, config)
    observed = market_sessions_after(state["last_session"], day, previous)
    result = copy.deepcopy(state)
    late = []
    for i, session in enumerate(observed[1:], start=1):
        prior = observed[i - 1]
        needed = {ticker for book in result["books"].values()
                  for ticker in set(book["positions"]) | set(book["pending"])}
        frames, today = fetch_live(config, session, prior, symbols, required=needed)
        # A missing held-price in ONE portfolio must not prevent eight
        # unrelated portfolios from observing their exact historic session.
        # The unpriced portfolio is quarantined, retaining its last real NAV;
        # a later observed price never skips/replaces its missing old session.
        decisions, coverage = rank_signals(config, frames, session)
        unfilled_buys = sorted({ticker for book in result["books"].values()
                               for ticker, order in book["pending"].items()
                               if order["side"] == "buy" and ticker not in today})
        coverage["unfilled_pending_buys_missing_bar"] = unfilled_buys
        coverage["verified_price_source_aliases"] = {
            t: b["verified_price_source_symbol"] for t, b in today.items()
            if "verified_price_source_symbol" in b}
        # An original signal dated prior must settle ONLY at this session's
        # verified open; new signals are frozen after its close, not before.
        settled, changed = settle(config, result, session, prior, today, allow_partial=True)
        paused = {name: book["paused_missing_quotes"]
                  for name, book in settled["books"].items()
                  if book.get("paused_missing_quotes")}
        coverage["paused_books_missing_held_quotes"] = {
            name: issue["missing_tickers"] for name, issue in paused.items()
        }
        if not changed:
            raise ValueError("Repeated reconciliation session")
        coverage["late_recorded_verified_date"] = True
        coverage["reconciliation_kind"] = "deterministic_frozen_signal_replay"
        result = freeze(config, settled, session, decisions, coverage)
        late.append(session)
    result.setdefault("late_recorded_sessions", []).extend(late)
    result["reconciliation_note"] = (
        "Late paper calculations from exact historical market bars and "
        "previously frozen strategy policies; original scheduled runs failed."
    )
    return result, late


def _dated_bar(frame, session, ticker):
    """Never substitute another session's OHLC or a previous close."""
    row = market._last_row(frame, session, ticker)
    return {"open": market._positive(row["Open"], "open"),
            "high": market._positive(row["High"], "high"),
            "low": market._positive(row["Low"], "low"),
            "close": market._positive(row["Close"], "close"),
            "split": float(row.get("Stock Splits", 0)),
            "dividend": float(row.get("Dividends", 0))}


def fetch_live(config, session, previous, symbols, required=()):
    start = (datetime.fromisoformat(session) - timedelta(days=config["execution"]["history_calendar_days"])).date().isoformat()
    end = (datetime.fromisoformat(session) + timedelta(days=1)).date().isoformat()
    frames = market._download(symbols + [config["benchmark_ticker"]], start, end, allow_missing=True)
    today = {}
    for ticker, frame in frames.items():
        try:
            today[ticker] = _dated_bar(frame, session, ticker)
        except (ValueError, TypeError, KeyError):
            continue

    # Yahoo bulk downloads can return an unusable OHLC column for an otherwise
    # active constituent, particularly within 40-symbol batches. Retry ONLY
    # existing positions and next-open pending orders as isolated reads.
    # Keep the frozen universe, eligibility denominator and strict dated-price
    # contract unchanged. Missing held/sell bars remain fatal; missing new BUY
    # bars are explicitly recorded as unfilled rather than backdated.
    for ticker in sorted(set(required) - set(today)):
        alias = verified_price_symbol(ticker, session)
        for source in [ticker] + ([alias] if alias else []):
            try:
                recovered = market._download([source], start, end, allow_missing=True)
                frame = recovered.get(source)
                if frame is None:
                    continue
                row = _dated_bar(frame, session, ticker)
            except (ValueError, TypeError, KeyError):
                continue
            if source != ticker:
                # Price only, verified issuer rename; never synthesize the bar
                # or create a trade under the new display symbol.
                row["verified_price_source_symbol"] = source
            frames[ticker] = frame
            today[ticker] = row
            break
    # Canonical current-session marks are reused only when the direct feed
    # lacks a valid dated bar. Existing direct values are never silently
    # overwritten on provider revisions or snapshot corruption.
    today, _common_diagnostic = overlay_common_ohlc(
        session, today, ROOT / "market_data" / "snapshots")
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
        from recovery import recover_passive_books
        from market_data.revisions import load_effective

        def sessions_after(start, end):
            import pandas_market_calendars as calendars
            days = calendars.get_calendar("XNYS").valid_days(start_date=start, end_date=end)
            return [str(value.date()) for value in days if str(value.date()) > start]

        def quotes(session):
            record = load_effective(ROOT / "market_data/snapshots", session)
            return record["bars"], {"snapshot_sha256": record["base"]["sha256"],
                                   "effective_sha256": record["effective_sha256"]}

        state, recovered, blocked = recover_passive_books(
            config, state, sessions_after, quotes,
            recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            reviews=market.read(ROOT / "market_data/corporate_action_reviews.json"))
        validate_state(state, config)
        if day <= state["last_session"]:
            if recovered:
                market.atomic_write(state_path, state)
            return {"status": "passive_marks_recovered" if recovered else "already_recorded",
                    "session": day, "recovered_books": recovered,
                    "recovery_blocked": blocked}
    gap = state is not None and previous != state["last_session"]
    if gap and any(book["positions"] for book in state["books"].values()):
        # Never skip held exposures or treat future prices as historic prices.
        # Reconcile the exact missed XNYS sessions in memory; publish atomically
        # only after all their mandatory bars and signal coverage have passed.
        reconciled, late = reconcile_invested_gap(
            config, state, day, previous, symbols)
        market.atomic_write(state_path, reconciled)
        paused_books = sorted(name for name, book in reconciled["books"].items()
                              if book.get("paused_missing_quotes"))
        return {"status": ("dated_paper_sessions_reconciled_partial"
                           if paused_books else "dated_paper_sessions_reconciled"),
                "date": day, "late_recorded_sessions": late,
                "books": len(reconciled["books"]),
                "paused_books": paused_books,
                "eligible": reconciled["coverage"][-1]["eligible"],
                "universe": reconciled["coverage"][-1]["total"]}
    # No stale next-open order may be filled after its intended session.
    needed = {ticker for book in state["books"].values()
              for ticker in set(book["positions"]) | set(book["pending"])} if state and not gap else set()
    frames, today = fetch_live(config, day, previous, symbols, required=needed)
    decisions, coverage = rank_signals(config, frames, day)
    if gap:
        recovered, missed, expired = recover_flat_gap(
            config, state, day, previous, decisions, coverage)
        market.atomic_write(state_path, recovered)
        return {"status": "flat_gap_recovered_no_backfill", "date": day,
                "missed_sessions": missed, "expired_pending_orders": expired,
                "eligible": coverage["eligible"], "universe": coverage["total"]}
    if state is None:
        fresh = initialize(config, day, decisions, coverage)
        market.atomic_write(state_path, fresh)
        return {"status": "first_signal_frozen", "date": day, "eligible": coverage["eligible"],
                "universe": coverage["total"]}
    # Persist explicit execution quality, without silently reducing the frozen
    # 503-symbol denominator or inventing a price for missing BUY candidates.
    unfilled_buys = sorted({ticker for book in state["books"].values()
                            for ticker, order in book["pending"].items()
                            if order["side"] == "buy" and ticker not in today})
    coverage["unfilled_pending_buys_missing_bar"] = unfilled_buys
    coverage["verified_price_source_aliases"] = {
        t: b["verified_price_source_symbol"] for t, b in today.items()
        if "verified_price_source_symbol" in b}
    updated, changed = settle(config, state, day, previous, today, allow_partial=True)
    paused = {name: item["paused_missing_quotes"]
              for name, item in updated["books"].items()
              if item.get("paused_missing_quotes")}
    coverage["paused_books_missing_held_quotes"] = {
        name: info["missing_tickers"] for name, info in paused.items()}
    if changed:
        updated = freeze(config, updated, day, decisions, coverage)
        market.atomic_write(state_path, updated)
    return {"status": "paper_recorded_partial" if paused else "paper_recorded",
            "date": day, "eligible": coverage["eligible"],
            "universe": coverage["total"], "models": len(config["strategies"]),
            "paused_books": sorted(paused),
            "unfilled_pending_buys_missing_bar": unfilled_buys}


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
