"""Live adapters for the Buy The Dip corpus paper strategy.

The campaign is forward-only. The universe is frozen in Git and observations are
captured prospectively from public market/accounting data. No broker connectivity.
"""

from __future__ import annotations

import csv
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


def load_universe(path):
    rows = list(csv.DictReader(Path(path).read_text(encoding="utf-8").splitlines()))
    if not rows or not {"symbol", "security", "sector"} <= set(rows[0]):
        raise ValueError("Universo congelado inválido")
    symbols = [row["symbol"].strip() for row in rows if row["symbol"].strip()]
    if len(symbols) != len(set(symbols)):
        raise ValueError("Símbolos duplicados en universo Buy The Dip")
    sectors = {row["symbol"].strip(): row["sector"].strip() for row in rows}
    names = {row["symbol"].strip(): row["security"].strip() for row in rows}
    return symbols, sectors, names


def eligible_session(calendar_name="XNYS", now=None):
    now = now or datetime.now(timezone.utc)
    import pandas_market_calendars as calendars

    calendar = calendars.get_calendar(calendar_name)
    local = now.astimezone(ZoneInfo("America/New_York"))
    schedule = calendar.schedule(
        start_date=local.date() - timedelta(days=14),
        end_date=local.date() + timedelta(days=14),
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
        raise ValueError("No se pudo resolver próxima apertura")
    next_open = upcoming.iloc[0]["market_open"].to_pydatetime()
    if now >= next_open:
        raise ValueError("La siguiente sesión ya abrió; no registrar retrospectivamente")
    return session.date().isoformat()


def calendar_context(asof, calendar_name="XNYS"):
    import pandas_market_calendars as calendars

    day = datetime.fromisoformat(asof).date()
    calendar = calendars.get_calendar(calendar_name)
    schedule = calendar.schedule(start_date=day - timedelta(days=5), end_date=day + timedelta(days=10))
    index = [session.date() for session in schedule.index]
    if day not in index:
        raise ValueError("asof no es sesión XNYS")
    pos = index.index(day)
    if pos + 1 >= len(index):
        raise ValueError("No se pudo resolver siguiente sesión")
    next_day = index[pos + 1]
    return {
        "is_month_end": next_day.month != day.month,
        "next_session": next_day.isoformat(),
    }


def _extract_download(data, ticker):
    if data is None or data.empty:
        return None
    if isinstance(data.columns, pd.MultiIndex):
        level0 = set(data.columns.get_level_values(0))
        level1 = set(data.columns.get_level_values(1))
        if ticker in level0:
            frame = data[ticker].copy()
        elif ticker in level1:
            frame = data.xs(ticker, level=1, axis=1).copy()
        else:
            return None
    else:
        frame = data.copy()
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required <= set(frame.columns):
        return None
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if frame.empty:
        return None
    adj = frame["Adj Close"] if "Adj Close" in frame.columns else frame["Close"]
    out = pd.DataFrame(index=pd.DatetimeIndex(frame.index).tz_localize(None))
    out["open"] = frame["Open"].to_numpy(dtype=float)
    out["high"] = frame["High"].to_numpy(dtype=float)
    out["low"] = frame["Low"].to_numpy(dtype=float)
    out["close"] = frame["Close"].to_numpy(dtype=float)
    out["adj_close"] = adj.to_numpy(dtype=float)
    out["volume"] = frame["Volume"].fillna(0).to_numpy(dtype=float)
    out["dividend"] = frame["Dividends"].fillna(0).to_numpy(dtype=float) if "Dividends" in frame.columns else 0.0
    out["split"] = frame["Stock Splits"].fillna(0).to_numpy(dtype=float) if "Stock Splits" in frame.columns else 0.0
    out = out[~out.index.duplicated(keep="last")].sort_index()
    valid = np.isfinite(out[["open", "high", "low", "close"]]).all(axis=1)
    valid &= (out[["open", "high", "low", "close"]] > 0).all(axis=1)
    return out.loc[valid]


def download_panel(tickers, *, period, asof, min_history=1):
    import yfinance as yf

    tickers = list(dict.fromkeys(tickers))
    panel, failures = {}, {}
    for start in range(0, len(tickers), 60):
        chunk = tickers[start:start + 60]
        data = yf.download(
            chunk, period=period, interval="1d", auto_adjust=False, actions=True,
            group_by="ticker", threads=True, progress=False,
        )
        for ticker in chunk:
            frame = _extract_download(data, ticker)
            if frame is None:
                failures[ticker] = "download_empty"
                continue
            frame = frame.loc[frame.index.date <= datetime.fromisoformat(asof).date()]
            if frame.empty or frame.index[-1].date().isoformat() != asof:
                failures[ticker] = "missing_asof"
                continue
            if len(frame) < min_history:
                failures[ticker] = f"history_{len(frame)}"
                continue
            panel[ticker] = frame
    return panel, failures


def current_bar(frame):
    row = frame.iloc[-1]
    return {key: float(row[key]) for key in ("open", "high", "low", "close", "volume", "dividend", "split")}


def close_series(frame):
    return [float(x) for x in frame["adj_close"].to_numpy(dtype=float)]


def _annual_map(frame, names):
    if frame is None or frame.empty:
        return {}
    for name in names:
        if name in frame.index:
            series = pd.to_numeric(frame.loc[name], errors="coerce").dropna()
            result = {}
            for stamp, value in series.items():
                try:
                    day = pd.Timestamp(stamp).date().isoformat()
                    number = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(number):
                    result[day] = number
            return result
    return {}


def _market_cap(instrument):
    try:
        value = instrument.fast_info.get("market_cap")
        if value is not None and math.isfinite(float(value)) and float(value) > 0:
            return float(value)
    except Exception:
        pass
    try:
        value = instrument.get_info().get("marketCap")
        if value is not None and math.isfinite(float(value)) and float(value) > 0:
            return float(value)
    except Exception:
        pass
    return None


def _one_fundamental(ticker, asof):
    import yfinance as yf

    instrument = yf.Ticker(ticker)
    balance = instrument.balance_sheet
    income = instrument.financials
    cashflow = instrument.cash_flow

    maps = {
        "assets": _annual_map(balance, ["Total Assets"]),
        "equity": _annual_map(balance, ["Stockholders Equity", "Total Equity Gross Minority Interest"]),
        "debt": _annual_map(balance, ["Total Debt"]),
        "cash": _annual_map(balance, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"]),
        "revenue": _annual_map(income, ["Total Revenue", "Operating Revenue"]),
        "operating_income": _annual_map(income, ["Operating Income", "EBIT"]),
        "interest_expense": _annual_map(income, ["Interest Expense", "Interest Expense Non Operating"]),
        "ocf": _annual_map(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"]),
        "capex": _annual_map(cashflow, ["Capital Expenditure", "Capital Expenditures"]),
        "repurchases": _annual_map(cashflow, [
            "Repurchase Of Capital Stock", "Repurchase Of Stock", "Common Stock Repurchase"
        ]),
        "issuance": _annual_map(cashflow, [
            "Issuance Of Capital Stock", "Common Stock Issuance", "Issuance Of Stock"
        ]),
    }
    required = ("assets", "revenue", "ocf", "capex")
    common = set.intersection(*(set(maps[key]) for key in required)) if all(maps[key] for key in required) else set()
    common = [day for day in common if day <= asof]
    dates = sorted(common, reverse=True)[:4]
    periods = []
    for day in dates:
        row = {"date": day}
        for key, values in maps.items():
            value = values.get(day)
            if key == "capex" and value is not None:
                value = abs(value)
            row[key] = value
        periods.append(row)
    return {
        "ticker": ticker,
        "market_cap": _market_cap(instrument),
        "periods": periods,
    }


def fundamentals_snapshot(tickers, sectors, *, asof, workers=8):
    data, failures = {}, {}
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futures = {pool.submit(_one_fundamental, ticker, asof): ticker for ticker in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                item = future.result()
                if len(item.get("periods") or []) < 3 or not item.get("market_cap"):
                    failures[ticker] = "fundamental_history_or_market_cap"
                    continue
                item["sector"] = sectors[ticker]
                data[ticker] = item
            except Exception as exc:
                failures[ticker] = type(exc).__name__
    return data, failures
