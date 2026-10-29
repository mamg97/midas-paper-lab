"""Audit the explicit migration allowlist, frozen cohorts and future diary appends."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXTRA_FILES = {"migration_manifest.json", "audit_publication.py", "session_gate.py",
               "training_check.py", "test_session_gate.py", "test_causality.py", "MIGRATION.md"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def audit():
    manifest = json.loads((ROOT / "migration_manifest.json").read_text())
    allowed = {entry["path"].split("genetic_invest_agent/", 1)[1] for entry in manifest["files"]} | EXTRA_FILES
    frozen = {"diario_portfolio.json", "diario_portfolio_forward.json"}
    for entry in manifest["files"]:
        if Path(entry["path"]).name in frozen:
            data = (ROOT / entry["path"].split("genetic_invest_agent/", 1)[1]).read_bytes()
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("Frozen simulated cohort changed")
    active = json.loads((ROOT / "registro_historico/diario_portfolio_forward_2026-10-12.json").read_text())
    anchor = manifest["active_anchor"]
    history = {day: value for day, value in active["equity_history"].items() if day <= anchor["last_session"]}
    if (len(history) != anchor["history_length"] or digest(history) != anchor["history_sha256"] or
            digest(active["trades"][:anchor["trade_count"]]) != anchor["trades_sha256"] or
            min(active["equity_history"]) != "2026-10-12" or active["initial_capital"] != 100000):
        raise ValueError("Canonical simulated history was rewritten")
    for relative in sorted(allowed):
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"Allowlisted component missing: {relative}")
        text = path.read_text(encoding="utf-8")
        if (re.search(r"(?:/Users/|/home/)[A-Za-z0-9_-]{3,}/", text) or
                re.search(r"gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}", text) or
                re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY", text) or
                re.search(r"\bES\d{22}\b", text) or
                re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", text)):
            raise ValueError(f"Potential private content in allowlist: {relative}")
    print(f"Publication audit passed: {len(allowed)} allowlisted files; frozen cohorts and active history preserved")


if __name__ == "__main__":
    audit()
