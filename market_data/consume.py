"""Read-only common price overlay. Never supplies signals or broker operations."""
from __future__ import annotations

import math
from pathlib import Path

from market_data.snapshot import load_snapshot, snapshot_path
from market_data.revisions import load_effective

RAW = ("open", "high", "low", "close", "dividend", "split")
# Allow numeric formatting noise, not economically material vendor revisions.
REL_TOL = 1e-8


def overlay(session: str, today: dict, root: Path) -> tuple[dict, dict]:
    """Prefer verified exact-session bars ONLY where the old adapter has none.

    On a disagreement, do not silently replace an existing live bar. Record
    the conflict for audit and retain the consumer's established behavior.
    All dates / SHA are checked by load_snapshot before trusting any row.
    """
    path = snapshot_path(root, session)
    if not path.is_file():
        return today.copy(), {"status": "snapshot_absent", "hash": None,
                              "reused": [], "conflicts": []}
    try:
        effective = load_effective(root, session)
        capture = effective["base"]
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return today.copy(), {"status": "snapshot_rejected",
                              "reason": type(exc).__name__, "hash": None,
                              "reused": [], "conflicts": []}

    result = {ticker: bar.copy() for ticker, bar in today.items()}
    reused, conflicts, verified = [], [], []
    for ticker, row in effective["bars"].items():
        converted = {key: row[key] for key in RAW}
        if row["provider_symbol"] != ticker:
            converted["verified_price_source_symbol"] = row["provider_symbol"]
        if ticker not in result:
            result[ticker] = converted
            reused.append(ticker)
            continue
        old = result[ticker]
        try:
            equal = all(math.isclose(float(old.get(key, 0)),
                                     converted[key], rel_tol=REL_TOL, abs_tol=1e-8)
                        for key in RAW)
        except (TypeError, ValueError, OverflowError):
            equal = False
        if equal:
            verified.append(ticker)
        else:
            conflicts.append(ticker)
    return result, {
        "status": "snapshot_read_only",
        "hash": capture["sha256"],
        "effective_sha256": effective["effective_sha256"],
        "revision_hashes": effective["revision_hashes"],
        "reused": sorted(reused),
        "verified": sorted(verified),
        "conflicts": sorted(conflicts),
        "snapshot_missing": sorted(effective["missing"]),
    }
