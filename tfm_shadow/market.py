"""Read-only, complete IBEX daily snapshot for TFM shadow forecasts."""

import math
import time as time_module
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def eligible_session(now=None):
    now = now or datetime.now(timezone.utc)
    madrid = now.astimezone(ZoneInfo("Europe/Madrid"))
    import pandas_market_calendars as calendars

    calendar = calendars.get_calendar("XMAD")
    schedule = calendar.schedule(start_date=madrid.date() - timedelta(days=10),
                                 end_date=madrid.date() + timedelta(days=10))
    eligible = []
    for session, row in schedule.iterrows():
        cutoff = datetime.combine(session.date(), time(20), tzinfo=ZoneInfo("Europe/Madrid"))
        if madrid >= cutoff:
            eligible.append(session)
    if not eligible:
        return None
    session = eligible[-1]
    upcoming = schedule.loc[schedule.index > session]
    if upcoming.empty or now >= upcoming.iloc[0]["market_open"].to_pydatetime():
        raise ValueError("La siguiente apertura ya ocurrió; no registrar señal retrospectiva")
    return session.date().isoformat()


def current_session_issues(raw_panel, asof, expected_tickers=None):
    """Return assets whose current-session bar is absent or unusable, without fabricating prices."""
    tickers = list(expected_tickers or raw_panel)
    missing, invalid = [], []
    for ticker in tickers:
        bars = raw_panel.get(ticker) or []
        bar = next((item for item in bars if item.get("date") == asof), None)
        if bar is None:
            missing.append(ticker)
            continue
        valid = all(isinstance(bar.get(field), (int, float)) and math.isfinite(bar[field]) and bar[field] > 0
                    for field in ("open", "close"))
        if not valid:
            invalid.append(ticker)
    return missing, invalid


def contiguous_complete_panel(raw_panel, expected_dates, asof, minimum=130):
    """Keep only the final uninterrupted block with valid observed OHLC for all assets."""
    by_ticker = {ticker: {bar["date"]: bar for bar in bars} for ticker, bars in raw_panel.items()}
    first = max(min(rows) for rows in by_ticker.values())
    dates = [day for day in expected_dates if first <= day <= asof]
    complete = []
    for day in dates:
        valid = all(day in rows and all(isinstance(rows[day][field], (int, float)) and
                                       math.isfinite(rows[day][field]) and rows[day][field] > 0
                                       for field in ("open", "close"))
                    for rows in by_ticker.values())
        complete.append(valid)
    if not dates or dates[-1] != asof:
        raise ValueError("La sesión objetivo no pertenece al calendario descargado")
    if not complete[-1]:
        missing, invalid = current_session_issues(raw_panel, asof)
        detail = []
        if missing:
            detail.append("sin barra: " + ",".join(missing))
        if invalid:
            detail.append("barra inválida: " + ",".join(invalid))
        suffix = "; ".join(detail) if detail else "cobertura incompleta"
        raise ValueError("Última sesión incompleta entre los 31 activos; " + suffix)
    start = max((index + 1 for index, valid in enumerate(complete) if not valid), default=0)
    usable = dates[start:]
    if len(usable) < minimum:
        raise ValueError(f"Historial continuo insuficiente: {len(usable)} sesiones completas")
    return {ticker: [rows[day] for day in usable] for ticker, rows in by_ticker.items()}


def live_panel(config, now=None):
    today = eligible_session(now)
    if today is None:
        return None
    import yfinance as yf

    raw_panel = {}
    errors = {}

    def download_one(ticker):
        instrument = yf.Ticker(ticker)
        data = instrument.history(period="3y", interval="1d", auto_adjust=False,
                                  actions=True, repair=False, raise_errors=True)
        if data is None or data.empty:
            raise ValueError("Sin datos")
        if instrument.get_history_metadata().get("currency") != "EUR":
            raise ValueError("Divisa distinta de EUR o ausente")
        return [{"date": index.date().isoformat(), "open": float(row["Open"]),
                 "close": float(row["Close"])}
                for index, row in data.iterrows() if index.date().isoformat() <= today]

    def refresh(tickers):
        for ticker in tickers:
            try:
                raw_panel[ticker] = download_one(ticker)
                errors.pop(ticker, None)
            except Exception as exc:
                raw_panel.pop(ticker, None)
                errors[ticker] = type(exc).__name__ + ":" + str(exc)

    refresh(config["tickers"])
    for attempt, delay in enumerate((8, 20), start=1):
        missing, invalid = current_session_issues(raw_panel, today, config["tickers"])
        retry = sorted(set(missing + invalid + list(errors)))
        if not retry:
            break
        print(f"TFM datos {today} incompletos para {','.join(retry)}; reintento {attempt}/2")
        time_module.sleep(delay)
        refresh(retry)

    missing, invalid = current_session_issues(raw_panel, today, config["tickers"])
    if missing or invalid or errors:
        detail = []
        if missing:
            detail.append("sin barra: " + ",".join(missing))
        if invalid:
            detail.append("barra inválida: " + ",".join(invalid))
        if errors:
            detail.append("errores: " + ",".join(f"{ticker}:{errors[ticker].split(':', 1)[0]}" for ticker in sorted(errors)))
        raise ValueError(f"Datos TFM no listos para {today} tras reintentos; " + "; ".join(detail))

    start = max(min(bar["date"] for bar in bars) for bars in raw_panel.values())
    import pandas_market_calendars as calendars
    schedule = calendars.get_calendar("XMAD").schedule(start_date=start, end_date=today)
    expected = list(schedule.index.strftime("%Y-%m-%d"))
    panel = contiguous_complete_panel(raw_panel, expected, today)
    if len(panel[config["tickers"][0]]) < len(expected):
        print("Se usa solo el tramo continuo completo del histórico; no se rellenan precios ausentes")
    return panel, today
