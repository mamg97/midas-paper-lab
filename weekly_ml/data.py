"""Point-in-time market snapshot and weekly features for MIDAS weekly ML."""

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


FEATURES = [
    "ret_5d", "ret_21d", "ret_63d", "ret_126d", "ret_252d",
    "vol_20d", "vol_63d",
    "sma20_ratio", "sma50_ratio", "sma200_ratio",
    "rsi14", "macd_norm", "bollinger_z", "atr14_ratio",
    "volume20_ratio", "gap_1d",
    "relative_21d", "relative_63d",
    "market_ret_21d", "market_ret_63d", "market_vol_20d",
] + [f"wret_lag_{i}" for i in range(1, 27)]


def load_universe(path):
    rows = list(csv.DictReader(Path(path).read_text(encoding="utf-8").splitlines()))
    if not rows or not {"symbol", "security", "sector"} <= set(rows[0]):
        raise ValueError("Universo S&P 500 inválido")
    symbols = [row["symbol"].strip() for row in rows if row["symbol"].strip()]
    if len(symbols) != len(set(symbols)):
        raise ValueError("Símbolos duplicados en el universo")
    sectors = {row["symbol"].strip(): row["sector"].strip() or "Unknown" for row in rows}
    return symbols, sectors


def eligible_session(now=None):
    """Latest NYSE session safely closed and still before the next opening."""
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
        # Give the data vendor time to publish the complete official daily bar.
        if now >= close + timedelta(minutes=90):
            eligible.append(session)
    if not eligible:
        return None
    session = eligible[-1]
    upcoming = schedule.loc[schedule.index > session]
    if upcoming.empty:
        raise ValueError("No se pudo resolver la próxima apertura XNYS")
    next_open = upcoming.iloc[0]["market_open"].to_pydatetime()
    if now >= next_open:
        raise ValueError("La próxima apertura ya ocurrió; no registrar señal retrospectiva")
    return session.date().isoformat()


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
    factor = (adj / frame["Close"]).replace([np.inf, -np.inf], np.nan)
    if factor.isna().any():
        factor = factor.fillna(1.0)
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
    symbols, sectors = load_universe(universe_path)
    requested = symbols + [x for x in config["benchmark_tickers"] if x not in symbols]

    import yfinance as yf

    panel = {}
    failures = {}
    chunk_size = 60
    for start in range(0, len(requested), chunk_size):
        chunk = requested[start:start + chunk_size]
        data = yf.download(
            chunk,
            period=config.get("history_period", "6y"),
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
            # Preserve the observed history even when the latest bar is missing.  A ticker
            # can then still settle a previously committed paper order without being
            # eligible for a new signal.  We never synthesize the missing latest bar.
            panel[ticker] = frame
            if frame.index[-1].date().isoformat() != asof:
                failures[ticker] = "missing_asof"
                continue
            if len(frame) < int(config["feature_min_history_days"]):
                failures[ticker] = f"history_{len(frame)}"
                continue

    for benchmark in config["benchmark_tickers"]:
        if benchmark not in panel:
            raise ValueError("Benchmark sin datos completos: " + benchmark)
    usable = [ticker for ticker in symbols if ticker in panel]
    if len(usable) < 350:
        raise ValueError(f"Universo utilizable demasiado pequeño: {len(usable)}")
    return panel, sectors, usable, failures, asof


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    value = 100 - 100 / (1 + rs)
    return value.fillna(50.0)


def _daily_features(frame, market):
    close = frame["close"]
    logret = np.log(close).diff()
    result = pd.DataFrame(index=frame.index)
    for name, periods in [("ret_5d", 5), ("ret_21d", 21), ("ret_63d", 63),
                          ("ret_126d", 126), ("ret_252d", 252)]:
        result[name] = close.pct_change(periods)
    result["vol_20d"] = logret.rolling(20).std() * math.sqrt(252)
    result["vol_63d"] = logret.rolling(63).std() * math.sqrt(252)
    for name, periods in [("sma20_ratio", 20), ("sma50_ratio", 50), ("sma200_ratio", 200)]:
        result[name] = close / close.rolling(periods).mean() - 1
    result["rsi14"] = (_rsi(close) - 50.0) / 50.0
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    result["macd_norm"] = (macd - signal) / close
    mean20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    result["bollinger_z"] = (close - mean20) / std20.replace(0, np.nan)
    prev_close = close.shift(1)
    true_range = pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - prev_close).abs(),
        (frame["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    result["atr14_ratio"] = true_range.rolling(14).mean() / close
    volume_mean = frame["volume"].rolling(20).mean()
    result["volume20_ratio"] = frame["volume"] / volume_mean.replace(0, np.nan) - 1
    result["gap_1d"] = frame["open"] / prev_close - 1

    aligned_market = market.reindex(frame.index).ffill()
    market_close = aligned_market["close"]
    market_logret = np.log(market_close).diff()
    market_21 = market_close.pct_change(21)
    market_63 = market_close.pct_change(63)
    result["relative_21d"] = result["ret_21d"] - market_21
    result["relative_63d"] = result["ret_63d"] - market_63
    result["market_ret_21d"] = market_21
    result["market_ret_63d"] = market_63
    result["market_vol_20d"] = market_logret.rolling(20).std() * math.sqrt(252)
    return result


def build_dataset(panel, sectors, usable, asof, minimum_live=300, minimum_labelled_weeks=52):
    """Return causal labelled rows plus one live row per usable ticker."""
    market = panel["SPY"]
    labelled = []
    live = []
    excluded = {}

    for ticker in usable:
        frame = panel[ticker].copy()
        features = _daily_features(frame, market)
        groups = [(period, block) for period, block in frame.groupby(frame.index.to_period("W-FRI"))
                  if not block.empty]
        weekly_closes = [float(block["close"].iloc[-1]) for _, block in groups]
        weekly_returns = [np.nan] + [
            math.log(weekly_closes[i] / weekly_closes[i - 1]) for i in range(1, len(weekly_closes))
        ]
        rows_for_ticker = 0
        for i, (_, block) in enumerate(groups):
            signal_date = block.index[-1]
            if signal_date.date().isoformat() > asof or i < 26:
                continue
            feature_row = features.loc[signal_date]
            lags = weekly_returns[max(1, i - 25):i + 1]
            if len(lags) != 26:
                continue
            values = {name: float(feature_row[name]) for name in FEATURES if not name.startswith("wret_lag_")}
            for lag, value in enumerate(reversed(lags), start=1):
                values[f"wret_lag_{lag}"] = float(value)
            if not all(math.isfinite(values[name]) for name in FEATURES):
                continue
            record = {
                "ticker": ticker,
                "sector": sectors.get(ticker, "Unknown"),
                "signal_date": signal_date.date().isoformat(),
                **values,
            }
            if i + 1 < len(groups):
                next_block = groups[i + 1][1]
                target_end_date = next_block.index[-1].date().isoformat()
                # A training label is legal only after the entire target week has
                # completed by the current signal cutoff.  This guard is what
                # prevents future bars appended to the input from changing past
                # training rows.
                if target_end_date <= asof:
                    target_open = float(next_block["open"].iloc[0])
                    target_close = float(next_block["close"].iloc[-1])
                    target = target_close / target_open - 1
                    if math.isfinite(target):
                        record.update(
                            target_return=float(target),
                            target_positive=int(target > 0),
                            target_end_date=target_end_date,
                        )
                        labelled.append(record)
                        rows_for_ticker += 1
            if signal_date.date().isoformat() == asof:
                live.append(record)
        if rows_for_ticker < minimum_labelled_weeks or not any(row["ticker"] == ticker for row in live):
            excluded[ticker] = "insufficient_feature_history_or_live_row"

    if not labelled or not live:
        raise ValueError("No se pudieron construir muestras semanales")
    labelled_df = pd.DataFrame(labelled)
    live_df = pd.DataFrame(live)
    valid_live = set(live_df["ticker"]) - set(excluded)
    labelled_df = labelled_df[labelled_df["ticker"].isin(valid_live)].reset_index(drop=True)
    live_df = live_df[live_df["ticker"].isin(valid_live)].reset_index(drop=True)
    if len(live_df) < minimum_live:
        raise ValueError(f"Demasiadas exclusiones de features: {len(live_df)} activos")
    return labelled_df, live_df, excluded


def execution_window(panel, ticker, signal_date):
    """First adjusted open and last adjusted close of the week after signal_date."""
    frame = panel[ticker]
    signal = pd.Timestamp(signal_date)
    signal_period = signal.to_period("W-FRI")
    later = frame.loc[frame.index > signal]
    if later.empty:
        return None
    groups = [(period, block) for period, block in later.groupby(later.index.to_period("W-FRI"))
              if period > signal_period and not block.empty]
    if not groups:
        return None
    period, block = groups[0]
    return {
        "week": str(period),
        "first_session": block.index[0].date().isoformat(),
        "last_session": block.index[-1].date().isoformat(),
        "open": float(block["open"].iloc[0]),
        "close": float(block["close"].iloc[-1]),
    }
