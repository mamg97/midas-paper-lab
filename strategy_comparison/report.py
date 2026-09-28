"""Expose every MIDAS idea without presenting missing strategies as live results."""

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _read(path, *, optional=False):
    path = Path(path)
    if optional and not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _config_hash(config):
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _equity(value, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError("Patrimonio inválido: " + label)
    return float(value)


def _daily_return(history, label):
    if len(history) < 2:
        return None
    previous = _equity(history[-2].get("nav"), label + " anterior")
    current = _equity(history[-1].get("nav"), label)
    if previous == 0:
        return None
    return round(100 * (current / previous - 1), 6)


TFM_IDS = {"tfm_lgbm_2023": "lgbm", "tfm_mlp_2023": "mlp",
           "tfm_lstm_2023": "lstm", "tfm_arima_2023": "arima"}


def build(registry, paper_config, paper_state=None, legacy_state=None, now=None,
          tfm_config=None, tfm_state=None):
    if registry.get("schema_version") != 1:
        raise ValueError("Versión de registro no válida")
    paper_names = registry.get("paper_tracks", {})
    if not isinstance(paper_names, dict) or set(paper_names) != set(paper_config.get("strategies", {})):
        raise ValueError("Registro y configuración paper no coinciden")
    ideas = registry.get("historical_ideas", [])
    legacy_tracks = registry.get("legacy_tracks", [])
    ids = list(paper_names) + [x["id"] for x in legacy_tracks + ideas]
    if len(ids) != len(set(ids)):
        raise ValueError("Ideas duplicadas")
    capital = _equity(paper_config.get("capital"), "capital inicial paper")
    if capital == 0:
        raise ValueError("Capital paper cero")
    if paper_state is not None:
        if paper_state.get("config_hash") != _config_hash(paper_config):
            raise ValueError("El diario paper pertenece a otra configuración")
        if set(paper_state.get("strategies", {})) != set(paper_names):
            raise ValueError("Faltan carteras paper")
    if tfm_config is not None:
        if set(tfm_config.get("models", [])) != set(TFM_IDS.values()):
            raise ValueError("Configuración TFM incompleta")
        if not TFM_IDS.keys() <= {item["id"] for item in ideas}:
            raise ValueError("El catálogo omite variantes TFM")
    if tfm_state is not None:
        if tfm_config is None or tfm_state.get("config_hash") != _config_hash(tfm_config):
            raise ValueError("El diario TFM pertenece a otra configuración")
        if set(tfm_state.get("models", {})) != set(TFM_IDS.values()):
            raise ValueError("Faltan carteras TFM")
    timestamp = now or datetime.now(timezone.utc)
    rows = []
    for strategy_id, label in paper_names.items():
        row = {"id": strategy_id, "label": label, "group": "paper_nuevo", "status": "programada_sin_diario",
               "first_session": None, "last_session": None, "initial_capital": capital, "last_equity": None,
               "return_pct": None, "day_return_pct": None, "currency": paper_config.get("currency", "USD"),
               "note": "Mismas reglas de contabilidad; variante nueva si el nombre indica adaptación."}
        if paper_state is not None:
            book = paper_state["strategies"][strategy_id]
            history = book.get("equity", [])
            if not history:
                raise ValueError("Cartera sin patrimonio: " + strategy_id)
            nav = _equity(history[-1].get("nav"), strategy_id)
            row.update(status="demo_con_diario" if book.get("status") == "active" else "pendiente_modelo",
                       first_session=paper_state.get("first_session"),
                       last_session=paper_state.get("last_session"), last_equity=nav,
                       return_pct=round(100 * (nav / capital - 1), 6),
                       day_return_pct=_daily_return(history, strategy_id))
        rows.append(row)
    for item in legacy_tracks:
        row = {"id": item["id"], "label": item["label"], "group": "diario_heredado",
               "status": "sin_diario_disponible", "first_session": None, "last_session": None,
               "initial_capital": None, "last_equity": None, "return_pct": None,
               "day_return_pct": None, "currency": None,
               "note": item["note"]}
        if item["id"] == "genetic_sp500_legacy" and legacy_state is not None:
            history = legacy_state.get("equity_history")
            if not isinstance(history, dict) or not history:
                raise ValueError("Diario genético sin patrimonio fechado")
            dates = sorted(history)
            initial = _equity(legacy_state.get("initial_capital"), "capital genético")
            if initial == 0:
                raise ValueError("Capital genético cero")
            nav = _equity(history[dates[-1]], "patrimonio genético")
            row.update(status="diario_heredado_observado", first_session=dates[0], last_session=dates[-1],
                       initial_capital=initial, last_equity=nav,
                       return_pct=round(100 * (nav / initial - 1), 6))
        rows.append(row)
    for item in ideas:
        if item["id"] in TFM_IDS and tfm_config is not None:
            row = {"id": item["id"], "label": item["label"] + " (versión corregida 2026)",
                   "group": "tfm_demo_adaptado", "status": "programada_sin_diario",
                   "first_session": None, "last_session": None,
                   "initial_capital": _equity(tfm_config["paper_policy"]["capital"], "capital TFM"),
                   "last_equity": None, "return_pct": None, "day_return_pct": None,
                   "currency": tfm_config.get("currency", "EUR"),
                   "note": "Modelo del TFM reimplementado; regla de cartera común provisional, distinta de la tesis.",
                   "kind": item["kind"], "source": item["source"]}
            if tfm_state is not None:
                book = tfm_state["models"][TFM_IDS[item["id"]]]
                nav = _equity(book.get("nav"), item["id"])
                if not book.get("equity") or book["equity"][-1].get("date") != tfm_state.get("last_session"):
                    raise ValueError("Patrimonio TFM sin fecha válida")
                capital_tfm = row["initial_capital"]
                row.update(status="demo_con_diario", first_session=tfm_state.get("first_session"),
                           last_session=tfm_state.get("last_session"), last_equity=nav,
                           return_pct=round(100 * (nav / capital_tfm - 1), 6),
                           day_return_pct=_daily_return(book["equity"], item["id"]))
            rows.append(row)
        else:
            rows.append({"id": item["id"], "label": item["label"], "group": "historica_pendiente",
                         "status": "sin_ejecucion_comparable", "first_session": None, "last_session": None,
                         "initial_capital": None, "last_equity": None, "return_pct": None,
                         "day_return_pct": None, "currency": None,
                         "note": item["blocker"], "kind": item["kind"], "source": item["source"]})
    return {"schema_version": 1, "generated_at_utc": timestamp.isoformat(),
            "principle": "No ordenar rentabilidades de carteras con distintas fechas de inicio o supuestos de ejecución.",
            "counts": {"paper_with_diary": sum(x["group"] == "paper_nuevo" and x["status"] == "demo_con_diario" for x in rows),
                       "legacy_with_diary": sum(x["status"] == "diario_heredado_observado" for x in rows),
                       "tfm_with_diary": sum(x["group"] == "tfm_demo_adaptado" and x["status"] == "demo_con_diario" for x in rows),
                       "historical_pending": sum(x["group"] == "historica_pendiente" for x in rows)}, "tracks": rows}


def markdown(report):
    lines = ["# MIDAS: todas las ideas en paralelo", "",
             "Actualizado: " + report["generated_at_utc"] + ". El tablero distingue resultados observados de ideas aún no ejecutadas.", "",
             "Las rentabilidades de la campaña nueva, el TFM adaptado y el diario genético antiguo **no forman una clasificación común**: empiezan en fechas distintas, usan divisas o reglas de ejecución distintas.", "",
             "| Línea | Estado | Primera fecha | Última fecha | Última sesión | Acumulada |", "| --- | --- | --- | --- | ---: | ---: |"]
    for row in report["tracks"]:
        value = "—" if row["return_pct"] is None else f"{row['return_pct']:.2f} %"
        daily = "—" if row["day_return_pct"] is None else f"{row['day_return_pct']:.2f} %"
        lines.append(f"| {row['label']} | {row['status']} | {row['first_session'] or '—'} | {row['last_session'] or '—'} | {daily} | {value} |")
    lines += ["", "## Qué impide activar las líneas restantes", ""]
    for row in report["tracks"]:
        if row["group"] == "historica_pendiente":
            lines.append(f"- **{row['label']}**: {row['note']}")
    lines += ["", "La [hoja de ruta](../research/ROADMAP.md) documenta el estado de las adaptaciones. Ninguna fila pendiente recibe rentabilidad simulada retrospectivamente.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tablero de todas las estrategias MIDAS")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--paper-config", required=True)
    parser.add_argument("--paper-state", required=True)
    parser.add_argument("--legacy-state")
    parser.add_argument("--tfm-config")
    parser.add_argument("--tfm-state")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = build(_read(args.registry), _read(args.paper_config),
                   _read(args.paper_state, optional=True), _read(args.legacy_state, optional=True) if args.legacy_state else None,
                   tfm_config=_read(args.tfm_config) if args.tfm_config else None,
                   tfm_state=_read(args.tfm_state, optional=True) if args.tfm_state else None)
    output = Path(args.output)
    _write(output / "dashboard.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    _write(output / "dashboard.md", markdown(report))
    print(json.dumps({"output": str(output), "counts": report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
