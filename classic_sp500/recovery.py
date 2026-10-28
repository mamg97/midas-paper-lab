"""Recover only passive marks; never create a historical decision or fill."""
from __future__ import annotations

import copy
import math


def recover_passive_books(config, state, sessions_after, quote_loader, *, recorded_at):
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
                nav = float(book["cash"])
                for ticker, pos in book["positions"].items():
                    row = bars[ticker]
                    if row.get("dividend", 0) or row.get("split", 0):
                        raise ValueError("corporate_action_requires_review")
                    close = float(row["close"])
                    if not math.isfinite(close) or close <= 0:
                        raise ValueError("invalid_close")
                    nav += pos["shares"] * close
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
