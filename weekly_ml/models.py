"""Causal weekly model ensemble for MIDAS.

Historical validation is chronological and diagnostic only. Live models are refit on every
label that is known at the signal cutoff, then used for the next-week paper forecast.
"""

import math

import numpy as np
import pandas as pd

from data import FEATURES


def _numeric_matrix(train, live):
    base_train = train[FEATURES].astype(float).copy()
    base_live = live[FEATURES].astype(float).copy()
    sectors = pd.concat([train["sector"], live["sector"]], ignore_index=True)
    dummies = pd.get_dummies(sectors, prefix="sector", dtype=float)
    train_dummies = dummies.iloc[: len(train)].reset_index(drop=True)
    live_dummies = dummies.iloc[len(train):].reset_index(drop=True)
    x_train = pd.concat([base_train.reset_index(drop=True), train_dummies], axis=1)
    x_live = pd.concat([base_live.reset_index(drop=True), live_dummies], axis=1)
    return x_train, x_live


def _chronological_split(labelled, validation_weeks):
    dates = sorted(labelled["signal_date"].unique())
    if len(dates) < validation_weeks + 60:
        raise ValueError("Muy pocas semanas para validación cronológica")
    val_dates = dates[-validation_weeks:]
    first_val = val_dates[0]
    train = labelled[labelled["target_end_date"] < first_val].copy()
    val = labelled[labelled["signal_date"].isin(val_dates)].copy()
    if train.empty or val.empty:
        raise ValueError("Split cronológico vacío")
    if train["target_end_date"].max() >= val["signal_date"].min():
        raise ValueError("Purga temporal insuficiente")
    return train, val


def _mae(y, pred):
    y = np.asarray(y, dtype=float)
    pred = np.asarray(pred, dtype=float)
    return float(np.mean(np.abs(y - pred)))


def _rank_ic(frame, score):
    working = frame[["signal_date", "target_return"]].copy()
    working["score"] = np.asarray(score, dtype=float)
    values = []
    for _, group in working.groupby("signal_date"):
        if len(group) < 20:
            continue
        a = group["score"].rank(pct=True).to_numpy(dtype=float)
        b = group["target_return"].rank(pct=True).to_numpy(dtype=float)
        if np.std(a) > 0 and np.std(b) > 0:
            values.append(float(np.corrcoef(a, b)[0, 1]))
    return None if not values else float(np.mean(values))


def _relevance(frame):
    out = pd.Series(index=frame.index, dtype=int)
    for _, idx in frame.groupby("signal_date").groups.items():
        ranks = frame.loc[idx, "target_return"].rank(pct=True, method="average")
        out.loc[idx] = np.minimum(4, np.floor(ranks * 5).astype(int))
    return out.astype(int)


def _lgbm_return(config, labelled, live, train, val):
    import lightgbm as lgb

    seed = int(config["training"]["seed"])
    estimators = int(config["training"]["lgbm_estimators"])
    rate = float(config["training"]["lgbm_learning_rate"])
    x_train, x_val = _numeric_matrix(train, val)
    model = lgb.LGBMRegressor(
        n_estimators=estimators,
        learning_rate=rate,
        num_leaves=31,
        max_depth=6,
        min_child_samples=40,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=2,
        verbosity=-1,
    )
    model.fit(
        x_train,
        train["target_return"],
        eval_set=[(x_val, val["target_return"])],
        callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    best = int(model.best_iteration_ or estimators)
    val_pred = model.predict(x_val, num_iteration=best)

    x_all, x_live = _numeric_matrix(labelled, live)
    final = lgb.LGBMRegressor(
        n_estimators=best,
        learning_rate=rate,
        num_leaves=31,
        max_depth=6,
        min_child_samples=40,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=2,
        verbosity=-1,
    )
    final.fit(x_all, labelled["target_return"])
    live_pred = final.predict(x_live)
    return (
        dict(zip(live["ticker"], map(float, live_pred))),
        {"mae": _mae(val["target_return"], val_pred),
         "rank_ic": _rank_ic(val, val_pred), "best_iteration": best},
    )


def _lgbm_direction(config, labelled, live, train, val):
    import lightgbm as lgb

    seed = int(config["training"]["seed"])
    estimators = int(config["training"]["lgbm_estimators"])
    rate = float(config["training"]["lgbm_learning_rate"])
    x_train, x_val = _numeric_matrix(train, val)
    model = lgb.LGBMClassifier(
        n_estimators=estimators,
        learning_rate=rate,
        num_leaves=31,
        max_depth=6,
        min_child_samples=40,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=2,
        verbosity=-1,
    )
    model.fit(
        x_train,
        train["target_positive"],
        eval_set=[(x_val, val["target_positive"])],
        callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    best = int(model.best_iteration_ or estimators)
    val_prob = model.predict_proba(x_val, num_iteration=best)[:, 1]
    val_class = (val_prob >= 0.5).astype(int)

    x_all, x_live = _numeric_matrix(labelled, live)
    final = lgb.LGBMClassifier(
        n_estimators=best,
        learning_rate=rate,
        num_leaves=31,
        max_depth=6,
        min_child_samples=40,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=2,
        verbosity=-1,
    )
    final.fit(x_all, labelled["target_positive"])
    live_prob = final.predict_proba(x_live)[:, 1]
    accuracy = float(np.mean(val_class == val["target_positive"].to_numpy(dtype=int)))
    brier = float(np.mean((val_prob - val["target_positive"].to_numpy(dtype=float)) ** 2))
    return dict(zip(live["ticker"], map(float, live_prob))), {
        "accuracy": accuracy,
        "brier": brier,
        "best_iteration": best,
    }


def _lgbm_ranker(config, labelled, live, train, val):
    import lightgbm as lgb

    seed = int(config["training"]["seed"])
    estimators = int(config["training"]["lgbm_estimators"])
    rate = float(config["training"]["lgbm_learning_rate"])

    train = train.sort_values(["signal_date", "ticker"]).reset_index(drop=True)
    val = val.sort_values(["signal_date", "ticker"]).reset_index(drop=True)
    x_train, x_val = _numeric_matrix(train, val)
    y_train = _relevance(train)
    y_val = _relevance(val)
    group_train = train.groupby("signal_date", sort=False).size().tolist()
    group_val = val.groupby("signal_date", sort=False).size().tolist()

    model = lgb.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=estimators,
        learning_rate=rate,
        num_leaves=31,
        max_depth=6,
        min_child_samples=40,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=2,
        verbosity=-1,
    )
    model.fit(
        x_train,
        y_train,
        group=group_train,
        eval_set=[(x_val, y_val)],
        eval_group=[group_val],
        eval_at=[10],
        callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    best = int(model.best_iteration_ or estimators)
    val_score = model.predict(x_val, num_iteration=best)

    ordered = labelled.sort_values(["signal_date", "ticker"]).reset_index(drop=True)
    x_all, x_live = _numeric_matrix(ordered, live)
    y_all = _relevance(ordered)
    group_all = ordered.groupby("signal_date", sort=False).size().tolist()
    final = lgb.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=best,
        learning_rate=rate,
        num_leaves=31,
        max_depth=6,
        min_child_samples=40,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=2,
        verbosity=-1,
    )
    final.fit(x_all, y_all, group=group_all)
    live_score = final.predict(x_live)
    return dict(zip(live["ticker"], map(float, live_score))), {
        "rank_ic": _rank_ic(val, val_score),
        "best_iteration": best,
    }


def _mlp_return(config, labelled, live, train, val):
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler

    seed = int(config["training"]["seed"])
    hidden = tuple(int(x) for x in config["training"]["mlp_hidden"])
    max_iter = int(config["training"]["mlp_max_iter"])
    x_train, x_val = _numeric_matrix(train, val)
    scale = StandardScaler().fit(x_train)
    y_mean = float(train["target_return"].mean())
    y_std = max(float(train["target_return"].std()), 1e-6)
    model = MLPRegressor(
        hidden_layer_sizes=hidden,
        max_iter=max_iter,
        batch_size=512,
        learning_rate_init=0.001,
        alpha=0.0005,
        random_state=seed,
        early_stopping=False,
    )
    model.fit(scale.transform(x_train), (train["target_return"] - y_mean) / y_std)
    val_pred = model.predict(scale.transform(x_val)) * y_std + y_mean

    x_all, x_live = _numeric_matrix(labelled, live)
    all_scale = StandardScaler().fit(x_all)
    all_mean = float(labelled["target_return"].mean())
    all_std = max(float(labelled["target_return"].std()), 1e-6)
    final = MLPRegressor(
        hidden_layer_sizes=hidden,
        max_iter=max_iter,
        batch_size=512,
        learning_rate_init=0.001,
        alpha=0.0005,
        random_state=seed,
        early_stopping=False,
    )
    final.fit(all_scale.transform(x_all), (labelled["target_return"] - all_mean) / all_std)
    live_pred = final.predict(all_scale.transform(x_live)) * all_std + all_mean
    return dict(zip(live["ticker"], map(float, live_pred))), {
        "mae": _mae(val["target_return"], val_pred),
        "rank_ic": _rank_ic(val, val_pred),
    }


def _lstm_return(config, labelled, live, train, val):
    import os

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf

    seed = int(config["training"]["seed"])
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(seed)
    lag_cols = [f"wret_lag_{i}" for i in range(1, 27)]

    def arrays(frame, mean=None, std=None, y_mean=None, y_std=None):
        x = frame[lag_cols].to_numpy(dtype=np.float32)
        if mean is None:
            mean = float(x.mean())
            std = max(float(x.std()), 1e-6)
        xx = ((x - mean) / std)[:, :, None]
        yy = None
        if "target_return" in frame:
            y = frame["target_return"].to_numpy(dtype=np.float32)
            if y_mean is None:
                y_mean = float(y.mean())
                y_std = max(float(y.std()), 1e-6)
            yy = (y - y_mean) / y_std
        return xx, yy, mean, std, y_mean, y_std

    x_train, y_train, mean, std, y_mean, y_std = arrays(train)
    x_val, _, _, _, _, _ = arrays(val, mean, std, y_mean, y_std)
    units = int(config["training"]["lstm_units"])
    epochs = int(config["training"]["lstm_epochs"])
    batch = int(config["training"]["lstm_batch_size"])
    model = tf.keras.Sequential([
        tf.keras.Input(shape=(26, 1)),
        tf.keras.layers.LSTM(units),
        tf.keras.layers.Dense(1),
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.002), loss="mae")
    model.fit(x_train, y_train, epochs=epochs, batch_size=batch, shuffle=False, verbose=0)
    val_pred = model.predict(x_val, verbose=0).ravel() * y_std + y_mean

    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(seed)
    x_all_raw = labelled[lag_cols].to_numpy(dtype=np.float32)
    mean_all = float(x_all_raw.mean())
    std_all = max(float(x_all_raw.std()), 1e-6)
    y_all_raw = labelled["target_return"].to_numpy(dtype=np.float32)
    y_mean_all = float(y_all_raw.mean())
    y_std_all = max(float(y_all_raw.std()), 1e-6)
    x_all = ((x_all_raw - mean_all) / std_all)[:, :, None]
    y_all = (y_all_raw - y_mean_all) / y_std_all
    x_live = ((live[lag_cols].to_numpy(dtype=np.float32) - mean_all) / std_all)[:, :, None]
    final = tf.keras.Sequential([
        tf.keras.Input(shape=(26, 1)),
        tf.keras.layers.LSTM(units),
        tf.keras.layers.Dense(1),
    ])
    final.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.002), loss="mae")
    final.fit(x_all, y_all, epochs=epochs, batch_size=batch, shuffle=False, verbose=0)
    live_pred = final.predict(x_live, verbose=0).ravel() * y_std_all + y_mean_all
    return dict(zip(live["ticker"], map(float, live_pred))), {
        "mae": _mae(val["target_return"], val_pred),
        "rank_ic": _rank_ic(val, val_pred),
    }


def _arima_return(config, live):
    from statsmodels.tsa.arima.model import ARIMA

    order = tuple(int(x) for x in config["training"]["arima_order"])
    lag_cols = [f"wret_lag_{i}" for i in range(26, 0, -1)]
    output = {}
    failures = 0
    for _, row in live.iterrows():
        series = row[lag_cols].to_numpy(dtype=float)
        try:
            fitted = ARIMA(
                series,
                order=order,
                trend="c",
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit()
            value = float(fitted.forecast(steps=1)[0])
            if not math.isfinite(value):
                raise ValueError()
        except Exception:
            failures += 1
            value = float(np.mean(series[-8:]))
        output[row["ticker"]] = value
    return output, {"live_fallbacks": failures, "validation": "not_run_to_limit_weekly_runtime"}


def _percentile(values):
    series = pd.Series(values, dtype=float)
    return series.rank(method="average", pct=True).to_dict()


def fit_predict(config, labelled, live):
    train, val = _chronological_split(labelled, int(config["validation_weeks"]))
    predictions = {}
    validation = {}

    predictions["lgbm_return"], validation["lgbm_return"] = _lgbm_return(config, labelled, live, train, val)
    predictions["lgbm_direction"], validation["lgbm_direction"] = _lgbm_direction(config, labelled, live, train, val)
    predictions["lgbm_ranker"], validation["lgbm_ranker"] = _lgbm_ranker(config, labelled, live, train, val)
    predictions["mlp_return"], validation["mlp_return"] = _mlp_return(config, labelled, live, train, val)
    predictions["lstm_return"], validation["lstm_return"] = _lstm_return(config, labelled, live, train, val)
    predictions["arima_return"], validation["arima_return"] = _arima_return(config, live)

    tickers = list(live["ticker"])
    for name, values in predictions.items():
        if set(values) != set(tickers):
            raise ValueError("Predicciones incompletas: " + name)

    regression_names = ["lgbm_return", "mlp_return", "lstm_return", "arima_return"]
    rank_inputs = regression_names + ["lgbm_direction", "lgbm_ranker"]
    percentiles = {name: _percentile(predictions[name]) for name in rank_inputs}
    ensemble = {}
    for ticker in tickers:
        votes = sum(predictions[name][ticker] > 0 for name in regression_names)
        votes += int(predictions["lgbm_direction"][ticker] >= 0.5)
        expected = float(np.median([predictions[name][ticker] for name in regression_names]))
        score = float(np.mean([percentiles[name][ticker] for name in rank_inputs]))
        dispersion = float(np.std([percentiles[name][ticker] for name in rank_inputs]))
        ensemble[ticker] = {
            "score": score,
            "predicted_return": expected,
            "positive_votes": int(votes),
            "rank_dispersion": dispersion,
        }
    predictions["ensemble_consensus"] = ensemble
    validation["ensemble_consensus"] = {
        "method": "equal_weight_cross_sectional_percentile_consensus",
        "note": "Prospective portfolio result is the acceptance metric; no historical ensemble return is injected.",
    }

    formatted = {}
    for name in config["models"]:
        formatted[name] = {}
        if name == "ensemble_consensus":
            formatted[name] = predictions[name]
            continue
        for ticker in tickers:
            value = float(predictions[name][ticker])
            row = {"score": value}
            if name == "lgbm_direction":
                row["direction_probability"] = value
            elif name == "lgbm_ranker":
                row["rank_score"] = value
            else:
                row["predicted_return"] = value
            formatted[name][ticker] = row
    return formatted, validation, {
        "train_rows": len(train),
        "validation_rows": len(val),
        "all_labelled_rows": len(labelled),
        "live_tickers": len(live),
        "train_last_target": str(train["target_end_date"].max()),
        "validation_first_signal": str(val["signal_date"].min()),
        "validation_last_signal": str(val["signal_date"].max()),
    }
