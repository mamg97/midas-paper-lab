"""Market data and corrected TFG signal construction."""

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


def load_universe(path):
    rows = list(csv.DictReader(Path(path).read_text(encoding="utf-8").splitlines()))
    if not rows or not {"symbol", "security", "sector"} <= set(rows[0]):
        raise ValueError("Universo TFG inválido")
    symbols = [row["symbol"].strip() for row in rows if row["symbol"].strip()]
    if len(symbols) != len(set(symbols)):
        raise ValueError("Símbolos duplicados en universo TFG")
    meta = {
        row["symbol"].strip(): {
            "security": row["security"].strip(),
            "sector": row["sector"].strip() or "Unknown",
        }
        for row in rows
        if row["symbol"].strip()
    }
    return symbols, meta


def eligible_session(now=None):
    """Latest safely closed XNYS session before the next open."""
    now = now or datetime.now(timezone.utc)
    import pandas_market_calendars as calendars

    calendar = calendars.get_calendar("XNYS")
    local = now.astimezone(ZoneInfo("America/New_York"))
    schedule = calendar.schedule(
        start_date=local.date() - timedelta(days=12),
        end_date=local.date() + timedelta(days=12),
    )
    eligible = []
    for session, row in schedule.iterrows():
        close = row["market_close"].to_pydatetime()
        if now >= close + timedelta(minutes=90):
            eligible.append(session)
    if not eligible:
        return None
    session = eligible[-1]
    upcoming = schedule.loc[schedule.index > session]
    if upcoming.empty:
        raise ValueError("No se pudo resolver la próxima apertura XNYS")
    if now >= upcoming.iloc[0]["market_open"].to_pydatetime():
        raise ValueError("La siguiente apertura ya ocurrió; no crear señal retrospectiva")
    return session.date().isoformat()


def is_week_end_session(asof):
    """True when asof is the last XNYS session whose week ends on Friday."""
    import pandas_market_calendars as calendars

    day = datetime.fromisoformat(asof).date()
    calendar = calendars.get_calendar("XNYS")
    schedule = calendar.schedule(
        start_date=day - timedelta(days=4),
        end_date=day + timedelta(days=4),
    )
    later_same_week = [
        idx.date()
        for idx in schedule.index
        if idx.date() > day and idx.to_period("W-FRI") == pd.Timestamp(day).to_period("W-FRI")
    ]
    return not later_same_week


def _extract_download(data, ticker):
    if data is None or data.empty:
        return None
    if isinstance(data.columns, pd.MultiIndex):
        if ticker not in data.columns.get_level_values(0):
            return None
        frame = data[ticker].copy()
    else:
        frame = data.copy()
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required <= set(frame.columns):
        return None
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if frame.empty:
        return None

    adj = frame["Adj Close"] if "Adj Close" in frame.columns else frame["Close"]
    factor = (adj / frame["Close"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)

    out = pd.DataFrame(index=pd.DatetimeIndex(frame.index).tz_localize(None))
    out["open"] = frame["Open"].to_numpy(dtype=float) * factor.to_numpy(dtype=float)
    out["high"] = frame["High"].to_numpy(dtype=float) * factor.to_numpy(dtype=float)
    out["low"] = frame["Low"].to_numpy(dtype=float) * factor.to_numpy(dtype=float)
    out["close"] = adj.to_numpy(dtype=float)
    out["volume"] = frame["Volume"].fillna(0).to_numpy(dtype=float)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    finite = np.isfinite(out[["open", "high", "low", "close"]]).all(axis=1)
    positive = (out[["open", "high", "low", "close"]] > 0).all(axis=1)
    return out.loc[finite & positive]


def live_panel(config, universe_path, now=None):
    asof = eligible_session(now)
    if asof is None:
        return None
    symbols, meta = load_universe(universe_path)
    requested = symbols + [x for x in config["benchmark_tickers"] if x not in symbols]

    import yfinance as yf

    panel = {}
    failures = {}
    for start in range(0, len(requested), 60):
        chunk = requested[start:start + 60]
        data = yf.download(
            chunk,
            period=config.get("history_period", "3y"),
            interval="1d",
            auto_adjust=False,
            actions=False,
            group_by="ticker",
            threads=True,
            progress=False,
        )
        for ticker in chunk:
            frame = _extract_download(data, ticker)
            if frame is None:
                failures[ticker] = "download_empty"
                continue
            frame = frame.loc[frame.index.date <= datetime.fromisoformat(asof).date()]
            if frame.empty:
                failures[ticker] = "empty_before_asof"
                continue
            panel[ticker] = frame
            if frame.index[-1].date().isoformat() != asof:
                failures[ticker] = "missing_asof"

    for benchmark in config["benchmark_tickers"]:
        if benchmark not in panel or panel[benchmark].index[-1].date().isoformat() != asof:
            raise ValueError("Benchmark sin cierre completo: " + benchmark)

    usable = [
        ticker for ticker in symbols
        if ticker in panel and panel[ticker].index[-1].date().isoformat() == asof
        and len(panel[ticker]) >= 280
    ]
    if len(usable) < 350:
        raise ValueError(f"Universo TFG utilizable demasiado pequeño: {len(usable)}")
    return panel, meta, usable, failures, asof


def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _tfg_rsi(close, n=14):
    """Literal TFG RSI: percentage of non-negative days in the rolling window."""
    delta = close.diff()
    up = (delta >= 0).astype(float)
    down = (delta < 0).astype(float)
    total = up.rolling(n).mean() + down.rolling(n).mean()
    return 100 * up.rolling(n).mean() / total.replace(0, np.nan)


def _slow_stochastic_close(close, n=14):
    low = close.rolling(n).min()
    high = close.rolling(n).max()
    fast_k = 100 * (close - low) / (high - low).replace(0, np.nan)
    return fast_k.rolling(3).mean()


def _bollinger_pct_b(close, n=20):
    mean = close.rolling(n).mean()
    std = close.rolling(n).std(ddof=0)
    upper = mean + 2 * std
    lower = mean - 2 * std
    return (close - lower) / (upper - lower).replace(0, np.nan)


def _technical_metrics(frame, config):
    close = frame["close"]
    t = config["technical"]
    window = int(t["window_days"])

    macd = _ema(close, 12) - _ema(close, 26)
    signal = _ema(macd, 9)
    macd_hist = macd - signal

    rsi = _tfg_rsi(close, 14)
    stochastic = _slow_stochastic_close(close, 14)
    pct_b = _bollinger_pct_b(close, 20)

    tail = pd.DataFrame({
        "macd": (macd_hist > 0).astype(float),
        "rsi": (rsi <= 30).astype(float),
        "stochastic": (stochastic <= 20).astype(float),
        "bollinger": (pct_b > 1).astype(float),
    }).tail(window)
    if len(tail) < window or tail.isna().any().any():
        return None

    ratios = {name: float(tail[name].mean()) for name in tail}
    passes = {
        "macd": ratios["macd"] > float(t["macd_threshold"]),
        "rsi": ratios["rsi"] > float(t["rsi_threshold"]),
        "stochastic": ratios["stochastic"] > float(t["stochastic_threshold"]),
        "bollinger": ratios["bollinger"] > float(t["bollinger_threshold"]),
    }
    return {
        **{f"{key}_ratio": value for key, value in ratios.items()},
        **{f"{key}_pass": value for key, value in passes.items()},
        "technical_pass": any(passes.values()),
    }


def _percentile(series, higher_is_better=True):
    value = series.astype(float)
    if not higher_is_better:
        value = -value
    return value.rank(method="average", pct=True)


def _cap_weights(raw_weights, invest_fraction, cap):
    """Cap weights iteratively and leave residual cash if capacity is insufficient."""
    weights = {ticker: 0.0 for ticker in raw_weights}
    positive = {ticker: max(float(value), 0.0) for ticker, value in raw_weights.items()}
    total_signal = sum(positive.values())
    if total_signal <= 0:
        equal = 1 / len(positive) if positive else 0
        positive = {ticker: equal for ticker in positive}
        total_signal = sum(positive.values())

    remaining = min(float(invest_fraction), len(positive) * float(cap))
    active = set(positive)
    signal = dict(positive)

    while active and remaining > 1e-12:
        denom = sum(signal[ticker] for ticker in active)
        if denom <= 0:
            proposed = {ticker: remaining / len(active) for ticker in active}
        else:
            proposed = {ticker: remaining * signal[ticker] / denom for ticker in active}
        capped = [ticker for ticker, value in proposed.items() if value > cap + 1e-12]
        if not capped:
            for ticker, value in proposed.items():
                weights[ticker] += value
            remaining = 0
            break
        for ticker in capped:
            allocation = min(cap - weights[ticker], remaining)
            if allocation > 0:
                weights[ticker] += allocation
                remaining -= allocation
            active.remove(ticker)
        if remaining <= 1e-12:
            break

    return weights


def build_signal(config, panel, meta, usable, asof):
    market = panel["SPY"]
    market_returns = market["close"].pct_change()

    rows = []
    return_days = int(config["multicriteria"]["return_days"])
    risk_days = int(config["multicriteria"]["risk_days"])
    beta_days = int(config["multicriteria"]["beta_days"])

    for ticker in usable:
        frame = panel[ticker]
        technical = _technical_metrics(frame, config)
        if technical is None:
            continue

        returns = frame["close"].pct_change().dropna()
        if len(returns) < max(return_days, risk_days, beta_days):
            continue

        recent = returns.tail(return_days)
        mean_return = float(recent.mean())
        mad = float((recent - mean_return).abs().mean())
        volatility = float(returns.tail(risk_days).std(ddof=1))

        aligned = pd.concat([
            returns.tail(beta_days).rename("stock"),
            market_returns.rename("market")
        ], axis=1).dropna().tail(beta_days)
        if len(aligned) < 120 or float(aligned["market"].var(ddof=1)) <= 0:
            continue
        beta = float(aligned["stock"].cov(aligned["market"]) / aligned["market"].var(ddof=1))
        if not all(math.isfinite(x) for x in (mean_return, mad, volatility, beta)):
            continue

        rows.append({
            "ticker": ticker,
            "security": meta[ticker]["security"],
            "sector": meta[ticker]["sector"],
            "asof": asof,
            **technical,
            "mean_daily_return": mean_return,
            "volatility_daily": volatility,
            "beta_spy": beta,
            "mad_40": mad,
        })

    table = pd.DataFrame(rows)
    if table.empty:
        return {
            "asof": asof,
            "status": "no_data",
            "universe_count": len(usable),
            "technical_candidates": 0,
            "stage2_candidates": 0,
            "selections": [],
            "diagnostics": [],
        }

    candidates = table[table["technical_pass"]].copy()
    minimum = int(config["portfolio"]["top_n"]) + 1
    if len(candidates) < minimum:
        return {
            "asof": asof,
            "status": "insufficient_technical_candidates",
            "universe_count": len(table),
            "technical_candidates": len(candidates),
            "stage2_candidates": 0,
            "selections": [],
            "diagnostics": table.sort_values(
                ["technical_pass", "macd_ratio"], ascending=[False, False]
            ).head(50).to_dict("records"),
        }

    candidates["return_score"] = _percentile(candidates["mean_daily_return"], True)
    candidates["low_vol_score"] = _percentile(candidates["volatility_daily"], False)
    candidates["low_beta_score"] = _percentile(candidates["beta_spy"], False)

    weights = config["multicriteria"]["weights"]
    candidates["ahp_corrected_score"] = (
        float(weights["return"]) * candidates["return_score"]
        + float(weights["low_volatility"]) * candidates["low_vol_score"]
        + float(weights["low_beta"]) * candidates["low_beta_score"]
    )

    stage2 = candidates.sort_values(
        ["ahp_corrected_score", "mean_daily_return"],
        ascending=[False, False]
    ).head(int(config["multicriteria"]["top_n"])).copy()

    stage2["utility_return_minus_mad"] = (
        stage2["mean_daily_return"]
        - float(config["portfolio"]["risk_aversion"]) * stage2["mad_40"]
    )
    stage2 = stage2.sort_values(
        ["utility_return_minus_mad", "ahp_corrected_score"],
        ascending=[False, False]
    ).reset_index(drop=True)

    n = int(config["portfolio"]["top_n"])
    if len(stage2) < n + 1:
        return {
            "asof": asof,
            "status": "insufficient_stage2_candidates",
            "universe_count": len(table),
            "technical_candidates": len(candidates),
            "stage2_candidates": len(stage2),
            "selections": [],
            "diagnostics": stage2.to_dict("records"),
        }

    selected = stage2.iloc[:n].copy()
    anchor = float(stage2.iloc[n]["utility_return_minus_mad"])
    best = float(selected.iloc[0]["utility_return_minus_mad"])
    denominator = best - anchor

    if denominator <= 1e-15:
        raw = {row.ticker: 1.0 for row in selected.itertuples()}
    else:
        raw = {
            row.ticker: max((float(row.utility_return_minus_mad) - anchor) / denominator, 0.0)
            for row in selected.itertuples()
        }

    final_weights = _cap_weights(
        raw,
        float(config["portfolio"]["invest_fraction"]),
        float(config["portfolio"]["max_position_weight"]),
    )

    selections = []
    for row in selected.itertuples():
        weight = float(final_weights[row.ticker])
        if weight <= 0:
            continue
        selections.append({
            "ticker": row.ticker,
            "security": row.security,
            "sector": row.sector,
            "weight": weight,
            "technical": {
                "macd_ratio": float(row.macd_ratio),
                "rsi_ratio": float(row.rsi_ratio),
                "stochastic_ratio": float(row.stochastic_ratio),
                "bollinger_ratio": float(row.bollinger_ratio),
            },
            "mean_daily_return": float(row.mean_daily_return),
            "volatility_daily": float(row.volatility_daily),
            "beta_spy": float(row.beta_spy),
            "ahp_corrected_score": float(row.ahp_corrected_score),
            "mad_40": float(row.mad_40),
            "utility_return_minus_mad": float(row.utility_return_minus_mad),
        })

    return {
        "asof": asof,
        "status": "signal",
        "universe_count": len(table),
        "technical_candidates": len(candidates),
        "stage2_candidates": len(stage2),
        "invested_weight": float(sum(item["weight"] for item in selections)),
        "selections": selections,
        "diagnostics": stage2.head(30).to_dict("records"),
    }


def target_week(frame, signal_date):
    signal = pd.Timestamp(signal_date)
    signal_period = signal.to_period("W-FRI")
    later = frame.loc[frame.index > signal]
    groups = [
        (period, block)
        for period, block in later.groupby(later.index.to_period("W-FRI"))
        if period > signal_period and not block.empty
    ]
    return None if not groups else groups[0][1].copy()
