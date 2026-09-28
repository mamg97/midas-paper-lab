"""Causal one-session forecasts inspired by the four TFM model families.

This is a corrected 2026 port, not the 2023 source code or its reported score.
"""

import csv
import gzip
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np


WINDOW = 50
SEED = 42


def read_csv(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    panel = defaultdict(list)
    with opener(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"date", "ticker", "open", "close"} <= set(reader.fieldnames or []):
            raise ValueError("Se requieren date, ticker, open y close")
        for row in reader:
            panel[row["ticker"]].append({"date": row["date"], "open": float(row["open"]),
                                         "close": float(row["close"])})
    return dict(panel)


def validate_panel(panel, asof, minimum=WINDOW + 80):
    if not isinstance(panel, dict) or not panel:
        raise ValueError("Panel vacío")
    try:
        if date.fromisoformat(asof).isoformat() != asof:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("asof inválida")
    reference = None
    for ticker, bars in sorted(panel.items()):
        if len(bars) < minimum:
            raise ValueError("Historial corto: " + ticker)
        dates = [bar["date"] for bar in bars]
        if len(dates) != len(set(dates)) or dates != sorted(dates) or dates[-1] != asof:
            raise ValueError("Fechas inválidas: " + ticker)
        if reference is None:
            reference = dates
        elif dates != reference:
            raise ValueError("Calendarios incompletos: " + ticker)
        for bar in bars:
            for field in ("open", "close"):
                value = bar[field]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                    raise ValueError("Precio inválido: " + ticker + "/" + field)
    return reference


def make_samples(panel, asof, window=WINDOW):
    dates = validate_panel(panel, asof, minimum=window + 80)
    features, targets, target_dates, tickers = [], [], [], []
    latest = {}
    for ticker, bars in sorted(panel.items()):
        closes = np.array([bar["close"] for bar in bars], dtype=np.float64)
        changes = np.diff(np.log(closes))
        for i in range(window, len(closes) - 1):
            features.append(changes[i - window:i])
            targets.append(changes[i])
            target_dates.append(dates[i + 1])
            tickers.append(ticker)
        latest[ticker] = {"features": changes[-window:], "close": float(closes[-1])}
    x = np.asarray(features, dtype=np.float32)
    y = np.asarray(targets, dtype=np.float32)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Muestras no finitas")
    if max(target_dates) != asof:
        raise ValueError("El entrenamiento debe acabar en el último cierre observado")
    return x, y, latest, {"samples": len(y), "first_target": min(target_dates),
                          "last_target": max(target_dates), "tickers": len(panel),
                          "window": window, "asof": asof}


def _lightgbm(x, y, latest):
    from lightgbm import LGBMRegressor

    model = LGBMRegressor(n_estimators=120, num_leaves=15, learning_rate=0.035,
                          min_child_samples=30, max_depth=5, random_state=SEED,
                          n_jobs=2, verbosity=-1)
    model.fit(x, y)
    tickers = sorted(latest)
    values = model.predict(np.stack([latest[t]["features"] for t in tickers]))
    return dict(zip(tickers, map(float, values)))


def _mlp(x, y, latest):
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler

    x_scale, y_scale = StandardScaler(), StandardScaler()
    xx = x_scale.fit_transform(x)
    yy = y_scale.fit_transform(y.reshape(-1, 1)).ravel()
    model = MLPRegressor(hidden_layer_sizes=(32,), batch_size=256, max_iter=300,
                         learning_rate_init=0.002, tol=1e-3, n_iter_no_change=15,
                         random_state=SEED)
    model.fit(xx, yy)
    tickers = sorted(latest)
    values = model.predict(x_scale.transform(np.stack([latest[t]["features"] for t in tickers])))
    unscaled = y_scale.inverse_transform(values.reshape(-1, 1)).ravel()
    return dict(zip(tickers, map(float, unscaled)))


def _lstm(x, y, latest):
    import os

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf

    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(SEED)
    mean, scale = float(np.mean(x)), float(np.std(x))
    scale = max(scale, 1e-6)
    xx = ((x - mean) / scale)[:, :, None]
    yy = (y - mean) / scale
    model = tf.keras.Sequential([tf.keras.Input(shape=(x.shape[1], 1)),
                                 tf.keras.layers.LSTM(16), tf.keras.layers.Dense(1)])
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.003), loss="mae")
    model.fit(xx, yy, epochs=3, batch_size=256, shuffle=False, verbose=0)
    tickers = sorted(latest)
    current = np.stack([latest[t]["features"] for t in tickers])
    values = model.predict(((current - mean) / scale)[:, :, None], verbose=0).ravel() * scale + mean
    return dict(zip(tickers, map(float, values)))


def _arima(panel):
    from statsmodels.tsa.ar_model import AutoReg

    results = {}
    for ticker, bars in sorted(panel.items()):
        log_closes = np.log(np.array([bar["close"] for bar in bars], dtype=np.float64))
        changes = np.diff(log_closes)
        # Conditional least squares form of ARIMA(1,1,0) with drift.
        model = AutoReg(changes, lags=1, trend="c").fit()
        results[ticker] = float(model.predict(start=len(changes), end=len(changes))[0])
    return results


def forecast(panel, asof, models=("lgbm", "mlp", "lstm", "arima")):
    x, y, latest, provenance = make_samples(panel, asof)
    output = {}
    for name in models:
        if name == "lgbm":
            estimates = _lightgbm(x, y, latest)
        elif name == "mlp":
            estimates = _mlp(x, y, latest)
        elif name == "lstm":
            estimates = _lstm(x, y, latest)
        elif name == "arima":
            estimates = _arima(panel)
        else:
            raise ValueError("Modelo desconocido: " + name)
        if set(estimates) != set(latest):
            raise ValueError("Predicciones incompletas: " + name)
        output[name] = {}
        for ticker, log_return in estimates.items():
            if not math.isfinite(log_return) or abs(log_return) > math.log(1.5):
                raise ValueError("Predicción inválida: " + name + "/" + ticker)
            current = latest[ticker]["close"]
            output[name][ticker] = {"last_close": current,
                                    "next_close_predicted": current * math.exp(log_return),
                                    "return_predicted_pct": 100 * math.expm1(log_return)}
    return {"schema_version": 1, "asof": asof, "currency": "EUR",
            "horizon": "next_market_session_close", "source_family": "TFM_2023_corrected_port_2026",
            "training": provenance, "models": output}
