"""Recover only passive marks; never create a historical decision or fill."""
from __future__ import annotations

import copy
import math


def reviewed_dividend(reviews, ticker, day, amount):
    for item in reviews.get("reviews", []):
        if (item.get("ticker") == ticker and item.get("vendor_ex_session") == day
                and item.get("kind") == "cash_dividend" and item.get("currency") == "USD"
                and item.get("amount") == amount and item.get("source_url", "").startswith("https://")
                and item.get("verified_on")):
            return item["source_url"]
    return None


def recover_passive_books(config, state, sessions_after, quote_loader, *, recorded_at, reviews=None):
    result = copy.deepcopy(state)
    recovered, blocked = [], {}
    for name, original in state["books"].items():
        if not original.get("paused_missing_quotes"):
            continue
        spec = config["strategies"].get(name, {})
        if (spec.get("kind") != "equal_weight_hold" and name != "benchmark_spy") or any(
            pos.get("stop") is not None or pos.get("target") is not None
            for pos in original["positions"].values()
        ) or any(order["side"] != "buy" for order in original["pending"].values()):
            blocked[name] = "historical_trading_rules_require_review"
            continue
        book = copy.deepcopy(original)
        days = sessions_after(book["equity"][-1]["date"], state["last_session"])
        if not days or days[-1] != state["last_session"]:
            blocked[name] = "incomplete_session_calendar"
            continue
        marks = []
        try:
            # Validate EVERY missing session before changing any part of a book.
            for day in days:
                bars, identity = quote_loader(day)
                if not set(book["positions"]) <= set(bars):
                    raise ValueError("missing_historical_held_bar")
                for ticker, pos in book["positions"].items():
                    row = bars[ticker]
                    dividend = float(row.get("dividend", 0))
                    if row.get("split", 0):
                        raise ValueError("corporate_action_requires_review")
                    if dividend:
                        source = reviewed_dividend(reviews or {}, ticker, day, dividend)
                        if not source or not math.isfinite(dividend) or dividend < 0:
                            raise ValueError("corporate_action_requires_review")
                        amount = pos["shares"] * dividend
                        book["cash"] += amount
                        pos["dividends"] = pos.get("dividends", 0) + amount
                        book["events"].append({"date": day, "type": "dividend",
                            "ticker": ticker, "amount": amount, "source_url": source,
                            "recorded_at_utc": recorded_at, "recognition": "existing_paper_ex_session_model"})
                    close = float(row["close"])
                    if not math.isfinite(close) or close <= 0:
                        raise ValueError("invalid_close")
                nav = float(book["cash"]) + sum(pos["shares"] * float(bars[ticker]["close"])
                                               for ticker, pos in book["positions"].items())
                if not math.isfinite(nav) or nav < 0:
                    raise ValueError("invalid_nav")
                marks.append({"date": day, "nav": nav, "late_mark_only": True,
                              "recorded_at_utc": recorded_at,
                              "quote_identity": identity})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            blocked[name] = str(exc)
            continue
        # These orders missed their intended open. Preserve their omission;
        # never execute them from a later historical or present-day quote.
        expired = sorted(book["pending"])
        book["pending"] = {}
        book["equity"].extend(marks)
        book["nav"] = marks[-1]["nav"]
        book["events"].append({"date": state["last_session"],
            "type": "passive_marks_recovered_no_fills",
            "recorded_at_utc": recorded_at, "sessions": days,
            "expired_unfilled_buys": expired})
        del book["paused_missing_quotes"]
        result["books"][name] = book
        recovered.append(name)
    return result, recovered, blocked
