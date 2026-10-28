"""Read-only source health, independent of strategy accounting/runtime success."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from market_data.snapshot import load_snapshot, snapshot_path
from market_data.revisions import load_effective


def inspect_source(root: Path, session: str, *, now=None) -> dict:
    """Inspect an explicitly expected session; never substitute an older file."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Health check time must be timezone-aware")
    path = snapshot_path(root, session)
    result = {"schema": "midas.xnys_source_health.v1", "market": "XNYS",
              "expected_session": session, "sha256": None,
              "captured_at_utc": None, "age_seconds": None,
              "coverage": None, "missing_symbols": None,
              "policy": "raw_exact_session_fallback_keep_existing_quotes",
              "engine_health": "not_assessed"}
    if not path.is_file():
        return {**result, "status": "snapshot_absent"}
    try:
        effective = load_effective(root, session)
        record = effective["base"]
        stamp = datetime.fromisoformat(record["captured_at_utc"].replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError("Capture timestamp is not UTC")
        age = (now - stamp).total_seconds()
        if age < 0:
            raise ValueError("Capture timestamp is in the future")
        if (now - _stamp(effective["last_captured_at_utc"])).total_seconds() < 0:
            raise ValueError("Revision timestamp is in the future")
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return {**result, "status": "snapshot_rejected"}
    return {**result, "status": "snapshot_verified",
            "sha256": record["sha256"], "captured_at_utc": record["captured_at_utc"],
            "effective_sha256": effective["effective_sha256"],
            "revision_hashes": effective["revision_hashes"],
            "age_seconds": int(age), "coverage": {
                "observed": len(effective["bars"]), "requested": 504,
                "missing": len(effective["missing"]),
                "frozen_constituents_observed": len(effective["bars"]) - int("SPY" in effective["bars"])},
            "missing_symbols": sorted(effective["missing"])}


def _stamp(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--root", type=Path, default=ROOT / "market_data/snapshots")
    args = parser.parse_args()
    result = inspect_source(args.root, args.session)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "snapshot_verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
