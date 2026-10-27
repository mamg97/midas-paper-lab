"""Prospective common XNYS daily OHLC capture; never executes orders or backfills."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_data.snapshot import make_snapshot, provider_symbol, write_immutable  # noqa: E402
from timesfm_strategy.run import _download, _last_row, calendar, load_universe  # noqa: E402

UNIVERSE = "weekly_ml/universe_sp500_2026-09-29.csv"
SNAPSHOTS = ROOT / "market_data" / "snapshots"
MAX_RETRIES = 18


def extract(frame, session: str, ticker: str) -> dict:
    """Use one exact-date RAW provider row, not adjusted/forward-filled closes."""
    row = _last_row(frame, session, ticker)
    return {
        "date": session, "open": row.get("Open"), "high": row.get("High"),
        "low": row.get("Low"), "close": row.get("Close"),
        "volume": row.get("Volume"),
        "dividend": row.get("Dividends", 0),
        "split": row.get("Stock Splits", 0),
    }


def collect(session: str, symbols: list[str], *,
            downloader=_download, attempts: int = MAX_RETRIES) -> tuple[dict, dict]:
    requested = sorted(set(symbols) | {"SPY"})
    translate = {symbol: provider_symbol(symbol, session) for symbol in requested}
    provider_names = sorted(set(translate.values()))
    start = (datetime.fromisoformat(session) - timedelta(days=6)).date().isoformat()
    end = (datetime.fromisoformat(session) + timedelta(days=1)).date().isoformat()
    panel = downloader(provider_names, start, end, allow_missing=True)
    found, missing = {}, {}

    for symbol in requested:
        source = translate[symbol]
        try:
            found[symbol] = extract(panel[source], session, source)
        except (ValueError, KeyError, TypeError) as exc:
            missing[symbol] = type(exc).__name__ + ": " + str(exc)[:120]

    # Do not permit a bad Yahoo batch to suppress unaffected instruments.
    # Recover missing provider tickers individually with a fixed cap; no stale
    # closes, cross-ticker substitutions, fake bars or unbounded Yahoo traffic.
    attempted = 0
    for source in sorted({translate[s] for s in missing}):
        if attempted >= attempts:
            break
        attempted += 1
        try:
            recovered = downloader([source], start, end, allow_missing=True)
            value = extract(recovered[source], session, source)
            for symbol in requested:
                if translate[symbol] == source and symbol in missing:
                    found[symbol] = value.copy()
                    del missing[symbol]
        except (ValueError, KeyError, TypeError) as exc:
            for symbol in requested:
                if translate[symbol] == source and symbol in missing:
                    missing[symbol] = "isolated_retry_" + type(exc).__name__
    return found, missing


def run():
    when = calendar()
    if when is None:
        return {"status": "session_not_eligible"}
    session, previous, next_session, _ = when
    symbols = load_universe(UNIVERSE)
    if len(symbols) != 503:
        raise ValueError("Frozen 503-symbol universe changed")
    found, missing = collect(session, symbols)
    # Do not persist a misleading canonical snapshot during major outages.
    count = sum(symbol in found for symbol in symbols)
    if count < math.ceil(len(symbols) * 0.90):
        raise ValueError("Provider outage: too few dated constituent OHLC " +
                         str(count) + "/503; no snapshot committed")
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot = make_snapshot(session, symbols, found, missing,
                             captured_at_utc=timestamp)
    path, created = write_immutable(SNAPSHOTS, snapshot)
    return {"status": "snapshot_written" if created else "snapshot_already_exists",
            "session": session, "path": str(path.relative_to(ROOT)),
            "sha256": snapshot["sha256"], "observed": len(found),
            "missing_count": len(missing),
            "missing_symbols": sorted(missing), "frozen_coverage": count,
            "previous_session": previous, "next_session": next_session}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("check", "capture"), default="check")
    args = parser.parse_args()
    try:
        if args.phase == "check":
            symbols = load_universe(UNIVERSE)
            if len(symbols) != 503 or len(set(symbols)) != 503:
                raise ValueError("Unusable frozen universe")
            print(json.dumps({"status": "valid", "frozen_universe": 503}))
            return 0
        print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print("MIDAS COMMON OHLC ERROR: " + repr(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
