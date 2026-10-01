"""Persist a tiny public runtime-health record for one scheduled MIDAS workflow."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


VALID_OUTCOMES = {"success", "failure", "cancelled", "skipped"}


def build_record(workflow_key, workflow_name, outcome, run_id, run_number, head_sha, recorded_at=None):
    if not workflow_key or not workflow_name:
        raise ValueError("workflow identity required")
    if outcome not in VALID_OUTCOMES:
        raise ValueError("unknown workflow outcome: " + str(outcome))
    if not str(run_id).isdigit() or not str(run_number).isdigit():
        raise ValueError("GitHub run identifiers must be numeric")
    stamp = recorded_at or datetime.now(timezone.utc).isoformat()
    if not isinstance(stamp, str) or not stamp:
        raise ValueError("recorded_at required")
    return {
        "schema_version": 1,
        "workflow_key": workflow_key,
        "workflow_name": workflow_name,
        "event": "schedule",
        "outcome": outcome,
        "run_id": int(run_id),
        "run_number": int(run_number),
        "head_sha": str(head_sha or "")[:40],
        "recorded_at_utc": stamp,
    }


def atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--workflow-key", required=True)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-number", required=True)
    parser.add_argument("--head-sha", default="")
    args = parser.parse_args(argv)
    record = build_record(
        args.workflow_key, args.workflow_name, args.outcome,
        args.run_id, args.run_number, args.head_sha,
    )
    atomic_write(args.output, record)
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
