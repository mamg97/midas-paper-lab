"""Run MIDAS weekly ML after the final US market close of the week."""

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
import pandas as pd

from data import build_dataset, live_panel
from models import fit_predict
from paper import advance, digest


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


def _installed_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        if name == "tensorflow":
            return version("tensorflow-cpu")
        raise


def _frame_digest(*frames):
    hasher = hashlib.sha256()
    for frame in frames:
        ordered = frame.sort_values(["signal_date", "ticker"]).reset_index(drop=True)
        hasher.update(ordered.to_csv(index=False, float_format="%.12g").encode("utf-8"))
    return hasher.hexdigest()


def _rank_ic(actual, score):
    a = pd.Series(score, dtype=float).rank(pct=True).to_numpy()
    b = pd.Series(actual, dtype=float).rank(pct=True).to_numpy()
    if len(a) < 20 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def evaluate(previous, panel, current_asof):
    # Diagnostic evaluation is not the book of executed trades. Missing vendor
    # quotes may be excluded here, but NEVER imputed or used to settle positions.
    from data import execution_window
    expected = previous["live_tickers"]
    actual = {}
    missing = {}
    for ticker in expected:
        if ticker not in panel:
            missing[ticker] = "vendor_history_unavailable"
            continue
        window = execution_window(panel, ticker, previous["asof"])
        if window is None:
            missing[ticker] = "next_week_window_unavailable"
            continue
        # A Thursday close cannot stand in for the actual Friday settlement.
        if window["last_session"] != current_asof:
            missing[ticker] = "weekly_final_close_unavailable"
            continue
        actual[ticker] = float(window["close"] / window["open"] - 1)

    if not actual:
        raise ValueError("Sin precios observados para evaluar el forecast semanal previo")
    coverage = len(actual) / len(expected)
    if len(expected) >= 100 and coverage < 0.90:
        raise ValueError(f"Cobertura de evaluación semanal insuficiente: {coverage:.1%}")

    metrics = {}
    for name, predictions in previous["models"].items():
        common = sorted(set(predictions) & set(actual))
        if not common:
            continue
        y = np.array([actual[ticker] for ticker in common], dtype=float)
        if name == "lgbm_direction":
            p = np.array([float(predictions[ticker]["direction_probability"]) for ticker in common])
            metrics[name] = {
                "accuracy": float(np.mean((p >= 0.5) == (y > 0))),
                "brier": float(np.mean((p - (y > 0).astype(float)) ** 2)),
                "rank_ic": _rank_ic(y, p),
            }
        elif name == "lgbm_ranker":
            score = np.array([float(predictions[ticker]["rank_score"]) for ticker in common])
            metrics[name] = {"rank_ic": _rank_ic(y, score)}
        elif name == "ensemble_consensus":
            score = np.array([float(predictions[ticker]["score"]) for ticker in common])
            pred = np.array([float(predictions[ticker]["predicted_return"]) for ticker in common])
            metrics[name] = {
                "mae": float(np.mean(np.abs(pred - y))),
                "direction_accuracy": float(np.mean((pred > 0) == (y > 0))),
                "rank_ic": _rank_ic(y, score),
            }
        else:
            pred = np.array([float(predictions[ticker]["predicted_return"]) for ticker in common])
            metrics[name] = {
                "mae": float(np.mean(np.abs(pred - y))),
                "direction_accuracy": float(np.mean((pred > 0) == (y > 0))),
                "rank_ic": _rank_ic(y, pred),
            }
    return {
        "schema_version": 1,
        "forecast_asof": previous["asof"],
        "evaluated_at_session": current_asof,
        "actual_tickers": len(actual),
        "expected_tickers": len(expected),
        "coverage_pct": round(100.0 * coverage, 4),
        "missing_tickers": missing,
        "metrics": metrics,
    }


def run(config_path, output_dir, now=None):
    config = _read(config_path)
    if config.get("schema_version") != 1 or config.get("calendar") != "XNYS":
        raise ValueError("Configuración weekly ML no admitida")
    if config.get("currency") != "USD":
        raise ValueError("La campaña weekly ML debe estar en USD")

    config_path = Path(config_path)
    root = config_path.parent.parent
    universe_path = root / config["universe_file"]
    snapshot = live_panel(config, universe_path, now=now)
    if snapshot is None:
        return {"status": "market_closed", "changed": False}
    panel, sectors, usable, market_failures, asof = snapshot

    out = Path(output_dir)
    forecast_dir = out / "forecasts"
    existing = sorted(forecast_dir.glob("????-??-??.json"))

    if existing and existing[-1].stem > asof:
        raise ValueError("Forecast semanal fuera de orden")
    if existing and existing[-1].stem == asof:
        previous = _read(existing[-1])
        if previous.get("config_hash") != digest(config):
            raise ValueError("Forecast previo pertenece a otra configuración")
        state_path = out / "ledger.json"
        if not state_path.exists():
            raise ValueError("Forecast semanal registrado sin ledger")
        state = _read(state_path)
        if state.get("config_hash") != digest(config) or state.get("last_session") != asof:
            raise ValueError("Ledger semanal desalineado con forecast ya registrado")
        if state.get("forecast_hash") != digest(previous):
            raise ValueError("Ledger semanal apunta a otro forecast")
        return {"status": "already_recorded", "session": asof, "changed": False}

    labelled, live, feature_exclusions = build_dataset(panel, sectors, usable, asof)
    input_digest = _frame_digest(labelled, live)

    state_path = out / "ledger.json"
    state = _read(state_path) if state_path.exists() else None
    if state is not None and state.get("config_hash") != digest(config):
        raise ValueError("Ledger semanal pertenece a otra configuración")

    if existing:
        previous = _read(existing[-1])
        if previous.get("config_hash") != digest(config):
            raise ValueError("Forecast previo pertenece a otra configuración")
        evaluation_path = out / "evaluations" / (previous["asof"] + ".json")
        evaluation = evaluate(previous, panel, asof)
        if evaluation_path.exists():
            if _read(evaluation_path) != evaluation:
                raise ValueError("Evaluación semanal histórica revisada")
        else:
            _write(evaluation_path, evaluation)

    predictions, validation, training = fit_predict(config, labelled, live)
    forecast = {
        "schema_version": 1,
        "asof": asof,
        "horizon": "next_week_first_open_to_last_close",
        "currency": "USD",
        "source_family": "MIDAS_v2_plus_TFM_corrected_weekly_ensemble_2026",
        "version": config["version"],
        "config_hash": digest(config),
        "input_digest": input_digest,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe_snapshot": {
            "configured": len(sectors),
            "download_usable": len(usable),
            "live_features": len(live),
            "market_failures": market_failures,
            "feature_exclusions": feature_exclusions,
        },
        "training": training,
        "validation": validation,
        "live_tickers": sorted(live["ticker"].tolist()),
        "models": predictions,
        "library_versions": {
            name: _installed_version(name)
            for name in ("yfinance", "pandas", "numpy", "lightgbm", "scikit-learn",
                         "tensorflow", "statsmodels")
        },
    }

    _write(forecast_dir / (asof + ".json"), forecast)
    state, _ = advance(config, panel, forecast, state)
    _write(state_path, state)
    return {
        "status": "forecast_recorded",
        "session": asof,
        "configured_universe": len(sectors),
        "live_tickers": len(live),
        "models": list(predictions),
        "paper_tracks": len(state["strategies"]),
        "changed": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="MIDAS weekly ML paper campaign")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args.config, args.output), ensure_ascii=False))
        return 0
    except Exception as exc:
        print("Error weekly ML: " + repr(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
