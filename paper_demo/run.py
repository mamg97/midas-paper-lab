"""Run a MIDAS paper campaign after a US session closes."""

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path

from engine import advance, digest, leaderboard
from market import live_snapshot


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run(config_path, output_dir, snapshot_path=None):
    config = _json(config_path)
    snapshot = _json(snapshot_path) if snapshot_path else live_snapshot(config)
    if snapshot is None:
        return {"status": "market_closed", "changed": False}
    if snapshot_path is None and snapshot.get("synthetic") is not False:
        raise ValueError("La campaña programada requiere datos de mercado no sintéticos")
    state_path = Path(output_dir) / "state.json"
    old = _json(state_path) if state_path.exists() else None
    updated, changed = advance(config, snapshot, old)
    if changed:
        snap_path = Path(output_dir) / "snapshots" / (snapshot["asof"] + ".json")
        if snap_path.exists():
            existing = _json(snap_path)
            old_hash = digest({"asof": existing["asof"], "bars": existing["bars"], "source": existing.get("source")})
            if old_hash != updated["market_hashes"][snapshot["asof"]]:
                raise ValueError("Existe otra captura distinta para esta fecha")
        else:
            _atomic_json(snap_path, snapshot)
        _atomic_json(state_path, updated)
    rows = leaderboard(config, updated)
    _atomic_json(Path(output_dir) / "leaderboard.json", rows)
    csv_path = Path(output_dir) / "leaderboard.csv"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=csv_path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, csv_path)
    return {"session": snapshot["asof"], "changed": changed, "leaderboard": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description="MIDAS: carteras demo sin órdenes reales")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--output", required=True)
    parser.add_argument("--snapshot", help="JSON local para prueba/repetición; sin red")
    args = parser.parse_args(argv)
    try:
        result = run(args.config, args.output, args.snapshot)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Error de campaña demo: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
