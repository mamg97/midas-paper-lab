"""Expose public paper source quality separately from consumer/runtime results."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from market_data.health import inspect_source

LEDGERS = {"classic_sp500": "classic_sp500_state/ledger.json",
           "buy_the_dip_strategy": "buy_the_dip_state/ledger.json",
           "capital_cycle": "capital_cycle_state/ledger.json",
           "weekly_ml_daily": "weekly_ml_daily_state/ledger.json",
           "timesfm_daily": "timesfm_state/ledger.json",
           "timesfm_one_day": "timesfm_daily_state/ledger.json"}


def summarize(root, session, outcomes, *, now=None):
    now = now or datetime.now(timezone.utc)
    result = inspect_source(root / "market_data/snapshots", session, now=now)
    result["checked_at_utc"] = now.isoformat()
    result["consumers"] = {}
    for name, relative in LEDGERS.items():
        status = outcomes.get("consume-" + name, {}).get("result", "not_observed")
        info = {"workflow_outcome": status, "updated_books": None, "paused_books": None,
                "ledger_status": "unavailable"}
        try:
            state = json.loads((root / relative).read_text())
            books = state.get("books", state.get("strategies"))
            if books is None:
                books = {name: state}
            dates = {key: (book.get("equity") or [{}])[-1].get("date", state.get("last_session"))
                     for key, book in books.items()}
            paused = [key for key, book in books.items()
                      if book.get("paused_missing_quotes") or dates[key] != session]
            info.update(updated_books=len(books) - len(paused), paused_books=len(paused),
                        paused_book_ids=sorted(paused), ledger_status="observed",
                        valuation_sessions=dates)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        result["consumers"][name] = info
    return result


def main():
    result = summarize(ROOT, os.environ["COMMON_SESSION"], json.loads(os.environ["COMMON_RESULTS"]))
    result["run_id"] = os.environ.get("GITHUB_RUN_ID")
    result["trigger_event"] = os.environ.get("GITHUB_EVENT_NAME")
    path = ROOT / "market_data/source_health.json"
    path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
