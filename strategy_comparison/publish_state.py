"""Publish one MIDAS state update without losing concurrent state-writer commits."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import sys
from pathlib import Path


DASHBOARD_CMD = [
    sys.executable, "strategy_comparison/report.py",
    "--registry", "strategy_comparison/registry.json",
    "--paper-config", "paper_demo/config.json",
    "--paper-state", "paper_state/state.json",
    "--tfm-config", "tfm_shadow/config.json",
    "--tfm-state", "tfm_state/ledger.json",
    "--weekly-ml-config", "weekly_ml/config.json",
    "--weekly-ml-state", "weekly_ml_state/ledger.json",
    "--weekly-ml-daily-state", "weekly_ml_daily_state/ledger.json",
    "--tfg-config", "tfg_ahp/config.json",
    "--tfg-state", "tfg_state/ledger.json",
    "--output", "strategy_state",
]
DASHBOARD_PATHS = ["strategy_state/dashboard.json", "strategy_state/dashboard.md"]


def git(*args, check=True, capture_output=False):
    return subprocess.run(["git", *args], check=check, text=True, capture_output=capture_output)


def commits_ahead_of_main():
    result = git("rev-list", "--count", "origin/main..HEAD", capture_output=True)
    return int(result.stdout.strip() or "0")


def refresh_dashboard():
    subprocess.run(DASHBOARD_CMD, check=True)


def existing(paths):
    return [path for path in paths if Path(path).exists()]


def runtime_rank(record):
    """Compare only GitHub scheduled run identity, never P&L or timestamp."""
    if not isinstance(record, dict) or record.get("event") != "schedule":
        return None
    try:
        run = int(record["run_number"])
        attempt = int(record.get("run_attempt", 1))
        if run < 1 or attempt < 1:
            return None
        return (record["workflow_key"], run, attempt)
    except (KeyError, TypeError, ValueError):
        return None


def should_restore_runtime(candidate, current):
    source, target = runtime_rank(candidate), runtime_rank(current)
    return (source is not None
            and (target is None or (source[0] == target[0]
            and source[1:] > target[1:])))


def preserve_newer_runtime(records):
    """Rebase keeps upstream for conflicts; restore only a truly newer owned run.

    Never overwrite a newer workflow attempt or another workflow's state.
    """
    changed = []
    for path, candidate in records.items():
        existing_record = None
        try:
            existing_record = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if should_restore_runtime(candidate, existing_record):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(
                json.dumps(candidate, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            changed.append(path)
    return changed


def publish(message, paths, attempts=8):
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    tracked = list(dict.fromkeys(existing(paths) + existing(DASHBOARD_PATHS)))
    # Save only public, owned runtime stamps before rebase. State writers may
    # concurrently update the same path; a later successful retry must survive.
    runtime_records = {}
    for path in tracked:
        if path.startswith("strategy_runtime/") and path.endswith(".json"):
            try:
                candidate = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if runtime_rank(candidate) is not None:
                runtime_records[path] = candidate
    if tracked:
        git("add", "--", *tracked)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("MIDAS publish: no changes")
        return 0

    git("commit", "-m", message)

    for attempt in range(1, attempts + 1):
        git("fetch", "origin", "main")
        # During rebase, "ours" is the updated upstream side. Shared dashboard
        # conflicts therefore prefer upstream; it is regenerated immediately below.
        git("rebase", "-X", "ours", "origin/main")

        # Si el rebase ha descartado nuestro commit porque exactamente el mismo
        # estado ya llegó a main desde otro run concurrente, el objetivo está
        # cumplido. No creemos un commit nuevo solo por regenerar dashboard.
        upstream_ahead = commits_ahead_of_main()
        restored = preserve_newer_runtime(runtime_records)
        if upstream_ahead == 0 and not restored:
            print(f"MIDAS publish: owned state already upstream on attempt {attempt}")
            return 0

        refresh_dashboard()
        tracked = list(dict.fromkeys(existing(paths) + existing(DASHBOARD_PATHS)))
        if tracked:
            git("add", "--", *tracked)
        staged = git("diff", "--cached", "--quiet", check=False).returncode != 0
        if upstream_ahead == 0:
            if not staged:
                print(f"MIDAS publish: no owned changes after rebase on attempt {attempt}")
                return 0
            git("commit", "-m", message)
        elif staged:
            git("commit", "--amend", "--no-edit")
        pushed = git("push", "origin", "HEAD:main", check=False)
        if pushed.returncode == 0:
            print(f"MIDAS publish: success on attempt {attempt}")
            return 0
        print(f"MIDAS publish: push race on attempt {attempt}/{attempts}")
        if attempt < attempts:
            time.sleep(min(3.0, float(attempt)))

    raise RuntimeError("MIDAS publish failed after retries")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", required=True)
    parser.add_argument("--path", action="append", default=[])
    args = parser.parse_args(argv)
    return publish(args.message, args.path)


if __name__ == "__main__":
    raise SystemExit(main())
