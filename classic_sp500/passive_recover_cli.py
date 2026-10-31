"""One-shot **passive valuation only** for quarantined classic books.

Never executes an order, invents a past signal, advances a live session, or
touches any unpaused portfolio. Requires all missing XNYS sessions' exact
SHA-verified OHLC from the common source before an atomic ledger write.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "classic_sp500"))
import run as classic  # noqa: E402
from recovery import recover_passive_books, reviewed_dividend  # noqa: E402
from market_data.revisions import load_effective  # noqa: E402
from timesfm_strategy.run import calendar  # noqa: E402


def recover(*, root=ROOT, write=False, clock=None):
    root = Path(root)
    config = classic.market.read(root / "classic_sp500/config.json")
    classic.verify_config(config)
    path = root / "classic_sp500_state/ledger.json"
    original = classic.market.read(path)
    classic.validate_state(original, config)
    when = calendar()
    if when is None:
        raise ValueError("No fully closed XNYS session")
    if original["last_session"] > when[0]:
        raise ValueError("Cannot reconcile a paper state from the future")

    def sessions_after(start, end):
        import pandas_market_calendars as calendars
        index = calendars.get_calendar("XNYS").valid_days(
            start_date=start, end_date=end)
        return [str(x.date()) for x in index if str(x.date()) > start]

    def quote_loader(day):
        effective = load_effective(root / "market_data/snapshots", day)
        return effective["bars"], {
            "snapshot_sha256": effective["base"]["sha256"],
            "effective_sha256": effective["effective_sha256"]}

    reviews = classic.market.read(root / "market_data/corporate_action_reviews.json")
    # Make accounting blockers visible to audit; do not auto-approve vendor
    # cash events, since record dates may differ from actual ex-dividend dates.
    pending_actions = []
    for name, book in original["books"].items():
        if not book.get("paused_missing_quotes"):
            continue
        for day in sessions_after(book["equity"][-1]["date"], original["last_session"]):
            bars, _identity = quote_loader(day)
            for ticker in sorted(book["positions"]):
                row = bars.get(ticker)
                if row is None:
                    continue
                div, split = float(row.get("dividend", 0)), float(row.get("split", 0))
                if split or div and not reviewed_dividend(reviews, ticker, day, div):
                    pending_actions.append({"book": name, "date": day, "ticker": ticker,
                                            "dividend": div, "split": split,
                                            "reason": "issuer_date_and_amount_review_required"})
    updated, completed, blocked = recover_passive_books(
        config, original, sessions_after, quote_loader,
        recorded_at=clock or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        reviews=reviews)
    for name, old in original["books"].items():
        new = updated["books"][name]
        if old["trades"] != new["trades"]:
            raise ValueError("Recovery attempted to modify historical fills")
        if name not in completed and old != new:
            raise ValueError("Recovery changed a book not proven complete")
        if name in completed:
            if set(old["positions"]) != set(new["positions"]):
                raise ValueError("Recovery attempted to change holdings")
            for ticker, old_pos in old["positions"].items():
                new_pos = new["positions"][ticker]
                if ({k: v for k, v in old_pos.items() if k != "dividends"} !=
                        {k: v for k, v in new_pos.items() if k != "dividends"}):
                    raise ValueError("Recovery changed non-dividend position economics")
    if updated["last_session"] != original["last_session"]:
        raise ValueError("Passive mark replay cannot change global market session")
    classic.validate_state(updated, config)
    if write and completed:
        classic.market.atomic_write(path, updated)
    return {"status": "passive_book_recovered" if completed and write else
                      "verified_recoverable" if completed else "nothing_recovered",
            "global_session": original["last_session"],
            "recovered_books": completed, "blocked_books": blocked,
            "unreviewed_corporate_actions": pending_actions,
            "written": bool(write and completed),
            "open_positions_unchanged": True, "trades_unchanged": True,
            "note": "late marks only; no trades, signals or NAV invented"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=("check", "recover"), default="check")
    args = p.parse_args()
    try:
        result = recover(write=args.phase == "recover")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print("MIDAS PASSIVE RECOVERY ERROR: " + repr(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
