"""Promote candidate corpus only when coverage does not regress."""

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

FILES = ("manifest.json", "corpus_features.json", "semantic_queue.json", "corpus_report.json", "corpus_report.md")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def coverage(report):
    return int(((report or {}).get("caption_coverage") or {}).get("available") or 0)

def promote(candidate_dir, state_dir):
    candidate_dir = Path(candidate_dir)
    state_dir = Path(state_dir)
    candidate = read_json(candidate_dir / "corpus_report.json")
    current_path = state_dir / "corpus_report.json"
    current = read_json(current_path) if current_path.exists() else None
    candidate_count = int(candidate.get("manifest_count") or 0)
    current_count = int((current or {}).get("manifest_count") or 0)
    candidate_coverage = coverage(candidate)
    current_coverage = coverage(current)
    if current is None:
        allowed, reason = True, "initial_state"
    elif candidate_count < current_count:
        allowed, reason = False, "candidate_manifest_regressed"
    elif candidate_coverage < current_coverage:
        allowed, reason = False, "candidate_caption_coverage_regressed"
    else:
        allowed, reason = True, "non_regressing_candidate"
    state_dir.mkdir(parents=True, exist_ok=True)
    if allowed:
        for name in FILES:
            src = candidate_dir / name
            if src.exists():
                shutil.copy2(src, state_dir / name)
    status = {
        "schema_version": 1,
        "attempted_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "promoted": allowed,
        "reason": reason,
        "candidate_manifest_count": candidate_count,
        "current_manifest_count_before": current_count,
        "candidate_caption_coverage": candidate_coverage,
        "current_caption_coverage_before": current_coverage,
        "caption_transport": candidate.get("caption_transport"),
    }
    (state_dir / "ingestion_status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return status

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(promote(args.candidate, args.state), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
