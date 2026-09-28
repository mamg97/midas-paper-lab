"""Append dated TFM predictions before the next session is observed."""

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from forecast import forecast, read_csv, validate_panel
from market import eligible_session, live_panel
from paper import advance


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _installed_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        if name == "tensorflow":
            return version("tensorflow-cpu")
        raise


def evaluate(previous, panel, current_asof):
    dates = [bar["date"] for bar in next(iter(panel.values()))]
    old_date = previous["asof"]
    if old_date not in dates or dates.index(old_date) == len(dates) - 1:
        raise ValueError("No se puede evaluar la próxima sesión de la predicción previa")
    next_day = dates[dates.index(old_date) + 1]
    if next_day > current_asof:
        raise ValueError("Evaluación futura")
    index = dates.index(next_day)
    rows = []
    for model, tickers in previous["models"].items():
        if set(tickers) != set(panel):
            raise ValueError("Universo previo incompleto")
        for ticker, predicted in tickers.items():
            last = float(predicted["last_close"])
            expected = float(predicted["next_close_predicted"])
            actual = float(panel[ticker][index]["close"])
            if not all(math.isfinite(x) and x > 0 for x in (last, expected, actual)):
                raise ValueError("Precio de evaluación inválido")
            predicted_return = expected / last - 1
            actual_return = actual / last - 1
            rows.append({"model": model, "ticker": ticker,
                         "predicted_return_pct": 100 * predicted_return,
                         "actual_return_pct": 100 * actual_return,
                         "absolute_return_error_pct": 100 * abs(predicted_return - actual_return),
                         "direction_correct": (predicted_return > 0) == (actual_return > 0)})
    return {"schema_version": 1, "forecast_asof": old_date, "outcome_session": next_day,
            "evaluated_at_session": current_asof, "recorded_after_gap": next_day != current_asof,
            "rows": rows}


def _reconcile_ledger(config, panel, output, forecast_files):
    ledger_path = output / "ledger.json"
    state = _read(ledger_path) if ledger_path.exists() else None
    for path in forecast_files:
        stored = _read(path)
        if stored.get("config_hash") != _digest(config):
            raise ValueError("Pronóstico de otra configuración")
        if state is not None and stored["asof"] <= state["last_session"]:
            continue
        day = stored["asof"]
        if set(stored.get("session_prices", {})) != set(panel):
            raise ValueError("La predicción no guarda todos los precios de su sesión")
        prefix = {ticker: [dict(bar) for bar in bars if bar["date"] <= day]
                  for ticker, bars in panel.items()}
        if any(not bars or bars[-1]["date"] != day for bars in prefix.values()):
            raise ValueError("No se puede recuperar una sesión fuera del historial")
        for ticker in prefix:
            prefix[ticker][-1].update(stored["session_prices"][ticker])
        state, _ = advance(config, prefix, stored, state)
        _write(ledger_path, state)
    if state is not None and (not forecast_files or state["last_session"] != _read(forecast_files[-1])["asof"]):
        raise ValueError("Diario TFM desalineado con los pronósticos")
    if state is not None and state.get("forecast_hash") != _digest(_read(forecast_files[-1])):
        raise ValueError("Pronóstico último distinto del registrado en el diario")
    return state


def run(config_path, output_dir, snapshot_csv=None):
    config = _read(config_path)
    if config.get("schema_version") != 1 or config.get("currency") != "EUR" or config.get("calendar") != "XMAD":
        raise ValueError("Configuración TFM no admitida")
    if config.get("models") != ["lgbm", "mlp", "lstm", "arima"] or len(config.get("tickers", [])) != 31:
        raise ValueError("Faltan modelos o activos del universo TFM")
    if snapshot_csv:
        panel = read_csv(snapshot_csv)
        asof = next(iter(panel.values()))[-1]["date"]
    else:
        snapshot = live_panel(config)
        if snapshot is None:
            return {"status": "market_closed", "changed": False}
        panel, asof = snapshot
    if set(panel) != set(config["tickers"]):
        raise ValueError("El universo descargado no coincide con el TFM configurado")
    validate_panel(panel, asof)
    fingerprint = _digest(panel)
    out = Path(output_dir)
    existing = sorted((out / "forecasts").glob("????-??-??.json"))
    if existing and existing[-1].stem > asof:
        raise ValueError("Sesión fuera de orden")
    if not existing and (out / "ledger.json").exists():
        raise ValueError("Diario sin pronósticos")
    state = _reconcile_ledger(config, panel, out, existing)
    previous = _read(existing[-1]) if existing else None
    if previous and previous.get("config_hash") != _digest(config):
        raise ValueError("La configuración cambió: iniciar otra campaña")
    if previous and previous["asof"] == asof:
        if previous.get("input_digest") != fingerprint:
            raise ValueError("Datos revisados para una predicción ya registrada")
        if len(existing) > 1:
            earlier = _read(existing[-2])
            evaluation_path = out / "evaluations" / (earlier["asof"] + ".json")
            if not evaluation_path.exists():
                _write(evaluation_path, evaluate(earlier, panel, asof))
        return {"status": "already_recorded", "session": asof, "changed": False}
    if previous:
        evaluation_path = out / "evaluations" / (previous["asof"] + ".json")
        evaluation = evaluate(previous, panel, asof)
        if evaluation_path.exists():
            if _read(evaluation_path) != evaluation:
                raise ValueError("Evaluación histórica revisada")
        else:
            _write(evaluation_path, evaluation)
    result = forecast(panel, asof, tuple(config["models"]))
    result["config_hash"] = _digest(config)
    result["input_digest"] = fingerprint
    result["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["session_prices"] = {ticker: {"open": rows[-1]["open"], "close": rows[-1]["close"]}
                                for ticker, rows in panel.items()}
    result["library_versions"] = {name: _installed_version(name) for name in
                                  ("lightgbm", "scikit-learn", "tensorflow", "statsmodels", "numpy")}
    if not snapshot_csv and eligible_session() != asof:
        raise ValueError("El pronóstico terminó después de la próxima apertura")
    _write(out / "forecasts" / (asof + ".json"), result)
    state, _ = advance(config, panel, result, state)
    _write(out / "ledger.json", state)
    return {"status": "forecast_recorded", "session": asof, "models": list(result["models"]),
            "tickers": len(panel), "paper_portfolios": len(state["models"]), "changed": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pronósticos TFM en modo sombra, sin bróker")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--output", required=True)
    parser.add_argument("--snapshot-csv", help="Captura CSV local para ensayo aislado")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args.config, args.output, args.snapshot_csv), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Error de pronóstico TFM: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
