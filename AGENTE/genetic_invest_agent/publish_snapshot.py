"""Send only dated simulated equity to the private MIDAS dashboard.

No positions, tickers, trades, Telegram credentials or raw diary are transmitted.
GitHub's short-lived OIDC token authenticates the scheduled workflow.
"""

import argparse
import hashlib
import json
import math
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DIARY = ROOT / "registro_historico" / "diario_portfolio.json"
# Old forward equity is an immutable archival cohort, not a continuation.
ARCHIVED_FORWARD_DIARY = ROOT / "registro_historico" / "diario_portfolio_forward.json"
FORWARD_DIARY = ROOT / "registro_historico" / "diario_portfolio_forward_2026-10-12.json"
ENDPOINT = "https://segundo-cerebro-midas-ingest.mamg97.workers.dev/v1/snapshot"
AUDIENCE = "segundo-cerebro-midas-legacy-ingest"


def build_payload(raw, strategy_id="genetic_sp500_legacy"):
    diary = json.loads(raw)
    if strategy_id not in {"genetic_sp500_legacy", "genetic_sp500_forward", "genetic_sp500_forward_archive"}:
        raise ValueError("Estrategia desconocida")
    if strategy_id in {"genetic_sp500_forward", "genetic_sp500_forward_archive"} and (diary.get("schema_version") != 1 or
                                                     diary.get("model") != "next_open_raw_ohlc_v1" or
                                                     diary.get("last_session") != max(diary.get("equity_history", {}) or {"": 0})):
        raise ValueError("Diario prospectivo inválido")
    capital = diary.get("initial_capital")
    history = diary.get("equity_history")
    if isinstance(capital, bool) or not isinstance(capital, (int, float)) or not math.isfinite(capital) or capital <= 0:
        raise ValueError("Capital inicial inválido")
    minimum = 1 if strategy_id != "genetic_sp500_legacy" else 2
    if not isinstance(history, dict) or not minimum <= len(history) <= 1000:
        raise ValueError("Historial de patrimonio inválido")
    points = []
    for day, equity in sorted(history.items()):
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or date.fromisoformat(day) > date.today():
            raise ValueError("Fecha de sesión inválida")
        if isinstance(equity, bool) or not isinstance(equity, (int, float)) or not math.isfinite(equity) or equity < 0:
            raise ValueError("Patrimonio inválido")
        points.append([day, float(equity)])
    return {
        "schema_version": 1,
        "strategy_id": strategy_id,
        "quality": "next_open_raw_ohlc_v1" if strategy_id != "genetic_sp500_legacy" else "legacy_same_close_model",
        "initial_capital": float(capital),
        "equity_history": points,
        "ledger_sha256": hashlib.sha256(raw).hexdigest(),
    }


def oidc_token():
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    separator = "&" if "?" in url else "?"
    request = Request(url + separator + "audience=" + quote(AUDIENCE, safe=""),
                      headers={"Authorization": "Bearer " + request_token, "Accept": "application/json"})
    with urlopen(request, timeout=15) as response:
        token = json.load(response).get("value")
    if not isinstance(token, str) or not token:
        raise RuntimeError("GitHub no entregó token OIDC")
    return token


def main():
    parser = argparse.ArgumentParser(description="Publicar un resumen demo privado del genético original")
    parser.add_argument("--check-only", action="store_true", help="Validar el diario sin red ni publicación")
    args = parser.parse_args()
    payloads = [build_payload(DIARY.read_bytes())]
    if ARCHIVED_FORWARD_DIARY.exists():
        payloads.append(build_payload(ARCHIVED_FORWARD_DIARY.read_bytes(),
                                      "genetic_sp500_forward_archive"))
    if FORWARD_DIARY.exists():
        payloads.append(build_payload(FORWARD_DIARY.read_bytes(), "genetic_sp500_forward"))
    if FORWARD_DIARY.exists():
        active = next(item for item in payloads if item["strategy_id"] == "genetic_sp500_forward")
        if active["equity_history"][0][0] != "2026-10-12":
            raise ValueError("Inicio de campaña genética nueva distinto de 2026-10-12")
        archive = next((item for item in payloads
                        if item["strategy_id"] == "genetic_sp500_forward_archive"), None)
        if archive is None or archive["equity_history"][-1][0] != "2026-10-07":
            raise ValueError("Archivo genético original ausente o alterado")
    for payload in payloads:
        latest = payload["equity_history"][-1][0]
        print(f"Diario {payload['strategy_id']} validado: {len(payload['equity_history'])} sesiones; última: {latest}")
    if args.check_only:
        return
    token = oidc_token()
    for payload in payloads:
        latest = payload["equity_history"][-1][0]
        request = Request(ENDPOINT, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/json", "Accept": "application/json",
                                   "User-Agent": "MIDAS-private-diary/1.0 (+GitHub Actions; mamg97)"},
                          method="POST")
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
        if result.get("ok") is not True or result.get("last_session") != latest or result.get("strategy_id") != payload["strategy_id"]:
            raise RuntimeError("El receptor MIDAS no confirmó la sesión")
        print(f"Resumen privado MIDAS actualizado: {payload['strategy_id']} {latest}")


if __name__ == "__main__":
    main()
