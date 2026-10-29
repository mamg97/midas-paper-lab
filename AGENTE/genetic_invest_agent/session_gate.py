"""Cheap, fail-closed preflight; do not spend time evolving an existing session."""
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from forward_portfolio import FILE_NAME, ensure_before_next_open, latest_completed_session, load


def session_due(path, session, check_open=ensure_before_next_open):
    if not Path(path).is_file():
        raise RuntimeError("Canonical forward diary missing; refusing to restart")
    state = load(path)
    if state["last_session"] == session:
        return False
    if not state["last_session"] or state["last_session"] > session:
        raise RuntimeError("Canonical diary does not precede the requested session")
    check_open(session)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        return
    session = latest_completed_session(datetime.now(timezone.utc).date().isoformat())
    due = session_due(Path(__file__).parent / "registro_historico" / FILE_NAME, session)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"due={str(due).lower()}\nsession={session}\n")
    print(f"Simulated session {session}: {'due' if due else 'already recorded'}")


if __name__ == "__main__":
    main()
