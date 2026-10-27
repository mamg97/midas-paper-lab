"""Immutable, provenance-bearing daily XNYS OHLC observations for paper strategies.

This module contains no broker access or trading decisions. Historical adjusted
series, fundamentals and FX remain separate data products.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA = "midas.xnys_ohlc.v1"
# Confirmed same security (not a replacement investment).
# SEC 8-K 2026-10-06: PSKY Class B -> SKYD, effective 2026-10-06.
RENAMES = {"PSKY": ("SKYD", "2026-10-06")}
FIELDS = ("open", "high", "low", "close", "volume", "dividend", "split")


def provider_symbol(symbol: str, session: str) -> str:
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Invalid canonical symbol")
    mapped = RENAMES.get(symbol)
    return mapped[0] if mapped and session >= mapped[1] else symbol.replace(".", "-")


def _day(session: str) -> str:
    try:
        if date.fromisoformat(session).isoformat() != session:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError("Session must be ISO YYYY-MM-DD") from exc
    return session


def _number(value, name, *, strictly_positive=False):
    try:
        n = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Bad " + name) from exc
    if not math.isfinite(n) or (n <= 0 if strictly_positive else n < 0):
        raise ValueError("Bad " + name)
    return n


def normalize_bar(row: dict, session: str, source_symbol: str) -> dict:
    """Reject missing, stale, impossible and non-finite vendor observations."""
    _day(session)
    if not isinstance(row, dict) or row.get("date") != session:
        raise ValueError("Missing exact dated XNYS bar")
    out = {"date": session, "provider_symbol": source_symbol}
    for key in FIELDS:
        out[key] = _number(row.get(key, 0 if key in ("dividend", "split") else None),
                           key, strictly_positive=key in ("open", "high", "low", "close"))
    if not (out["low"] <= out["open"] <= out["high"] and
            out["low"] <= out["close"] <= out["high"]):
        raise ValueError("Impossible OHLC range")
    return out


def _digest(data: dict) -> str:
    core = {k: v for k, v in data.items() if k != "sha256"}
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_snapshot(session: str, symbols: list[str], observations: dict,
                  failures: dict | None = None, *, captured_at_utc: str,
                  benchmark_symbols: tuple[str, ...] = ("SPY",)) -> dict:
    """Construct a single dated snapshot; never alter the frozen denominator."""
    _day(session)
    ordered = list(symbols)
    if len(ordered) != 503 or len(set(ordered)) != 503:
        raise ValueError("Frozen XNYS universe must have exactly 503 distinct IDs")
    targets = sorted(set(ordered) | set(benchmark_symbols))
    if len(targets) != 504:
        raise ValueError("Benchmark and universe must not overlap")
    try:
        timestamp = datetime.fromisoformat(captured_at_utc.replace("Z", "+00:00"))
        if timestamp.utcoffset().total_seconds() != 0:
            raise ValueError
    except (AttributeError, ValueError, TypeError) as exc:
        raise ValueError("Capture timestamp must have a UTC offset") from exc
    failures = failures or {}
    unexpected = (set(observations) | set(failures)) - set(targets)
    if unexpected:
        raise ValueError("Unexpected symbols: " + repr(sorted(unexpected)))
    entries, missing = {}, {}
    for symbol in targets:
        provider = provider_symbol(symbol, session)
        try:
            if symbol not in observations:
                raise ValueError("no_provider_bar")
            entries[symbol] = normalize_bar(observations[symbol], session, provider)
        except (ValueError, KeyError, TypeError) as exc:
            missing[symbol] = {"provider_symbol": provider,
                               "reason": str(failures.get(symbol) or str(exc))[:180]}
    snapshot = {
        "schema": SCHEMA, "market": "XNYS", "session": session,
        "captured_at_utc": captured_at_utc,
        "source": {"vendor": "Yahoo Finance", "client": "yfinance",
                   "interval": "1d", "auto_adjust": False, "actions": True},
        "universe_id": "sp500_frozen_2026-09-29",
        "frozen_universe_size": 503, "requested_symbols": targets,
        "coverage": {"observed": len(entries), "requested": len(targets),
                     "missing": len(missing),
                     "frozen_constituents_observed": sum(x in entries for x in ordered)},
        "bars": entries, "missing": missing,
    }
    snapshot["sha256"] = _digest(snapshot)
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict, *, session: str | None = None) -> None:
    """Fail closed on tampering, wrong-session data, coverage and bogus bars."""
    if not isinstance(snapshot, dict) or snapshot.get("schema") != SCHEMA:
        raise ValueError("Unsupported snapshot")
    day = _day(snapshot.get("session"))
    if session is not None and session != day:
        raise ValueError("Wrong XNYS session")
    if snapshot.get("market") != "XNYS" or snapshot.get("frozen_universe_size") != 503:
        raise ValueError("Wrong market or universe")
    names = snapshot.get("requested_symbols")
    bars, missing = snapshot.get("bars"), snapshot.get("missing")
    if (not isinstance(names, list) or len(names) != 504 or
            names != sorted(set(names)) or "SPY" not in names or
            not isinstance(bars, dict) or not isinstance(missing, dict) or
            set(bars).intersection(missing) or
            set(bars) | set(missing) != set(names)):
        raise ValueError("Invalid snapshot universe coverage")
    if (snapshot.get("coverage", {}).get("observed") != len(bars) or
            snapshot["coverage"].get("missing") != len(missing) or
            snapshot["coverage"].get("requested") != len(names) or
            snapshot["coverage"].get("frozen_constituents_observed") !=
            len(bars) - int("SPY" in bars)):
        raise ValueError("Invalid coverage counts")
    for symbol, row in bars.items():
        if normalize_bar(row, day, provider_symbol(symbol, day)) != row:
            raise ValueError("Noncanonical OHLC values")
    for symbol, detail in missing.items():
        if (not isinstance(detail, dict) or
                detail.get("provider_symbol") != provider_symbol(symbol, day) or
                not detail.get("reason")):
            raise ValueError("Invalid missing-price evidence")
    if not isinstance(snapshot.get("sha256"), str) or snapshot["sha256"] != _digest(snapshot):
        raise ValueError("Snapshot checksum mismatch")


def snapshot_path(root: Path, session: str) -> Path:
    return Path(root) / "XNYS" / (_day(session) + ".json")


def write_immutable(root: Path, snapshot: dict) -> tuple[Path, bool]:
    """Atomic create-only; conflict requires a *separate* reviewed revision."""
    validate_snapshot(snapshot)
    path = snapshot_path(root, snapshot["session"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = load_snapshot(path, session=snapshot["session"])
        if existing["sha256"] != snapshot["sha256"]:
            raise ValueError("Immutable session exists with different content")
        return path, False
    with tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                     dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        json.dump(snapshot, stream, sort_keys=True, indent=2,
                  ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(temp, path)  # exclusive atomic creation: never replace
        except FileExistsError:
            existing = load_snapshot(path, session=snapshot["session"])
            if existing["sha256"] != snapshot["sha256"]:
                raise ValueError("Concurrent different session snapshot")
            return path, False
    finally:
        temp.unlink(missing_ok=True)
    return path, True


def load_snapshot(path: Path, *, session: str) -> dict:
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_snapshot(snapshot, session=session)
    return snapshot
