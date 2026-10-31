"""Bounded recovery of genuinely missing HELD XNYS quotes.

Only appends provenance-linked price observations to previously recorded common
sessions. No fills, signals, cash, NAV, positions, or past ledger edits.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_data.collect import collect
from market_data.revisions import append_missing, load_effective
from market_data.snapshot import snapshot_path
from timesfm_strategy.run import calendar

SNAPSHOTS = ROOT / "market_data" / "snapshots"
LEDGER = ROOT / "classic_sp500_state" / "ledger.json"
MAX_SESSIONS = 4
MAX_REQUIRED_SYMBOLS = 20


def paused_requirements(ledger: dict) -> tuple[str, dict]:
    """Only exposures that really exist in the frozen paper book qualify."""
    cutoff = ledger.get("last_session")
    if not isinstance(cutoff, str):
        raise ValueError("Missing canonical classic last_session")
    result = {}
    for name, book in ledger.get("books", {}).items():
        issue = book.get("paused_missing_quotes")
        if not issue:
            continue
        since = issue.get("since")
        if not isinstance(since, str) or since > cutoff:
            raise ValueError("Invalid paused-book chronology")
        held = set(book.get("positions", {}))
        sells = {s for s, o in book.get("pending", {}).items()
                 if o.get("side") == "sell"}
        # Recovery must not invent a historical fill for a missing BUY.
        required = sorted(set(issue.get("missing_tickers", [])) & (held | sells))
        if not required:
            raise ValueError("Paused book lacks genuinely held missing exposure")
        for ticker in required:
            result.setdefault(ticker, since)
            result[ticker] = min(result[ticker], since)
    if len(result) > MAX_REQUIRED_SYMBOLS:
        raise ValueError("Too many held exposures for bounded recovery")
    return cutoff, result


def eligible_targets(root: Path, ledger: dict, eligible_session: str):
    """Select recent immutable sessions only; refuse future/unobserved days."""
    cutoff, held = paused_requirements(ledger)
    if not held:
        return []
    if eligible_session < cutoff:
        raise ValueError("Provider's last closed session is older than ledger")
    target = []
    for path in sorted((Path(root) / "XNYS").glob("????-??-??.json")):
        day = path.stem
        if not (min(held.values()) <= day <= cutoff <= eligible_session):
            continue
        relevant = [ticker for ticker, since in held.items() if since <= day]
        if relevant:
            target.append((day, relevant))
    # Conservatively refuse an unbounded outage; keep earliest gaps in view.
    return target[:MAX_SESSIONS]


def recover_one(root: Path, session: str, required: list[str], *,
                download=collect, timestamp=None):
    effective = load_effective(root, session)
    # No substitution of a different market, stale day, or price provider.
    base = effective["base"]
    if base["source"].get("vendor") != "Yahoo Finance":
        raise ValueError("Historical recovery must match the original provider")
    needed = sorted(set(required) & set(effective["missing"]))
    if not needed:
        return {"session": session, "status": "already_complete",
                "requested": required, "remaining": []}
    # Exact dated unadjusted Yahoo data, no broad historical re-simulation.
    found, failures = download(session, needed, include_benchmark=False)
    if not set(found) <= set(needed):
        raise ValueError("Provider returned unexpected recovery identities")
    # A dividend or split needs an issuer-specific separate review before NAV.
    ignored = sorted(x for x, row in found.items()
                     if row.get("dividend") or row.get("split"))
    valid = {x: row for x, row in found.items() if x not in ignored}
    if not valid:
        return {"session": session, "status": "still_missing",
                "requested": needed, "remaining": needed,
                "corporate_action_review": ignored}
    time = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")
    path, revision = append_missing(root, session, valid, captured_at_utc=time)
    return {"session": session, "status": "revision_written",
            "requested": needed, "recovered": sorted(valid),
            "remaining": sorted(set(needed) - set(valid)),
            "corporate_action_review": ignored, "sha256": revision["sha256"],
            "parent_sha256": revision["parent_sha256"],
            "revision_path": str(path)}


def execute(root=SNAPSHOTS, ledger_path=LEDGER, when=None, *, dry_run=False):
    when = when or calendar()
    if not when:
        return {"status": "no_eligible_closed_session"}
    latest = when[0]
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    candidates = eligible_targets(root, ledger, latest)
    if dry_run:
        # Read-only integrity checks before potentially expensive live Yahoo.
        out = []
        for day, tickers in candidates:
            effective = load_effective(root, day)
            out.append({"session": day, "required_missing": sorted(
                set(tickers) & set(effective["missing"]))})
        return {"status": "preflight", "candidates": out}
    details = [recover_one(root, day, tickers) for day, tickers in candidates]
    return {"status": "held_quote_recovery_checked",
            "eligible_session": latest, "results": details,
            "note": "No portfolio ledger or existing OHLC bar modified"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("check", "recover"), default="check")
    args = parser.parse_args()
    try:
        result = execute(dry_run=args.phase == "check")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("MIDAS HELD MARK RECOVERY ERROR: " + repr(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
