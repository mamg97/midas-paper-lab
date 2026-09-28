"""Read-only, complete IBEX daily snapshot for TFM shadow forecasts."""

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


def live_panel(config, now=None):
    today = eligible_session(now)
    if today is None:
        return None
    import yfinance as yf

    panel = {}
    for ticker in config["tickers"]:
        instrument = yf.Ticker(ticker)
        data = instrument.history(period="3y", interval="1d", auto_adjust=False,
                                  actions=True, repair=False, raise_errors=True)
        if data is None or data.empty:
            raise ValueError("Sin datos: " + ticker)
        if instrument.get_history_metadata().get("currency") != "EUR":
            raise ValueError("Divisa distinta de EUR o ausente: " + ticker)
        panel[ticker] = [{"date": index.date().isoformat(), "open": float(row["Open"]),
                          "close": float(row["Close"])}
                         for index, row in data.iterrows() if index.date().isoformat() <= today]
    if {bars[-1]["date"] for bars in panel.values()} != {today}:
        raise ValueError("Última sesión incompleta entre los 31 activos")
    return panel, today
