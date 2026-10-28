"""Append-only, hash-linked recovery of absent bars. Never revise an observed bar."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from market_data.snapshot import _digest, load_snapshot, normalize_bar, provider_symbol, snapshot_path

SCHEMA = "midas.xnys_missing_revision.v1"


def _timestamp(text):
    stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("Revision timestamp must be UTC")
    return stamp


def revision_dir(root, session):
    return snapshot_path(root, session).with_suffix(".revisions")


def load_effective(root, session):
    base = load_snapshot(snapshot_path(root, session), session=session)
    bars, missing = copy.deepcopy(base["bars"]), copy.deepcopy(base["missing"])
    children, records = {}, []
    for path in revision_dir(root, session).glob("*.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        if (item.get("schema") != SCHEMA or item.get("session") != session
                or item.get("base_sha256") != base["sha256"]
                or item.get("source") != base["source"]
                or item.get("sha256") != _digest(item)
                or path.stem != item["sha256"] or not item.get("bars")):
            raise ValueError("Invalid source revision identity")
        parent = item["parent_sha256"]
        if parent in children:
            raise ValueError("Ambiguous source revision branch")
        children[parent] = item
        records.append(item)
    head = base["sha256"]
    timestamp = _timestamp(base["captured_at_utc"])
    used = []
    while head in children:
        item = children[head]
        newer = _timestamp(item["captured_at_utc"])
        if newer < timestamp or not set(item["bars"]) <= set(missing):
            raise ValueError("Revision rewrites existing data or capture chronology")
        for symbol, row in item["bars"].items():
            normalized = normalize_bar(row, session, provider_symbol(symbol, session))
            if normalized != row or row["dividend"] or row["split"]:
                raise ValueError("Revision corporate action requires separate review")
            bars[symbol] = normalized
            del missing[symbol]
        head, timestamp = item["sha256"], newer
        used.append(head)
    if len(used) != len(records):
        raise ValueError("Unlinked source revision")
    return {"base": base, "bars": bars, "missing": missing,
            "effective_sha256": head, "revision_hashes": used,
            "last_captured_at_utc": timestamp.isoformat()}


def append_missing(root, session, observations, *, captured_at_utc):
    effective = load_effective(root, session)
    if not observations or not set(observations) <= set(effective["missing"]):
        raise ValueError("Revision must contain only genuinely missing symbols")
    base = effective["base"]
    if _timestamp(captured_at_utc) < _timestamp(effective["last_captured_at_utc"]):
        raise ValueError("Revision predates base capture")
    bars = {s: normalize_bar(r, session, provider_symbol(s, session))
            for s, r in observations.items()}
    if any(r["dividend"] or r["split"] for r in bars.values()):
        raise ValueError("Corporate action requires separate review")
    item = {"schema": SCHEMA, "session": session, "base_sha256": base["sha256"],
            "parent_sha256": effective["effective_sha256"],
            "captured_at_utc": captured_at_utc, "bars": bars,
            "source": base["source"].copy()}
    item["sha256"] = _digest(item)
    folder = revision_dir(root, session)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (item["sha256"] + ".json")
    # Exclusive creation: an existing file is never overwritten, even on races.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as stream:
        temp = Path(stream.name)
        json.dump(item, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    # A concurrent branch/conflict remains visible and fails closed on read.
    load_effective(root, session)
    return path, item
