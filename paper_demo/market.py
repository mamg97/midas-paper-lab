"""Yahoo daily-bar adapter; no trading APIs or credentials."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def live_snapshot(config, now=None):
    now = now or datetime.now(timezone.utc)
    eastern = now.astimezone(ZoneInfo("America/New_York"))
    if eastern.hour < 18:
        raise ValueError("Esperar al menos hasta las 18:00 de Nueva York para leer la barra diaria")
    import pandas_market_calendars as mcal
    import yfinance as yf

    today = eastern.date().isoformat()
    if mcal.get_calendar("NYSE").schedule(start_date=today, end_date=today).empty:
        return None

    panel = {}
    for ticker in config["tickers"] + config.get("benchmark_tickers", []):
        instrument = yf.Ticker(ticker)
        data = instrument.history(period="3y", interval="1d", auto_adjust=False,
                                  actions=True, repair=False, raise_errors=True)
        if data is None or data.empty:
            raise ValueError("Sin datos: " + ticker)
        metadata = instrument.get_history_metadata()
        if metadata.get("currency") != "USD":
            raise ValueError("Divisa ausente o distinta de USD: " + ticker)
        rows = []
        for index, row in data.tail(350).iterrows():
            day = index.date().isoformat()
            values = {"date": day, "open": float(row["Open"]), "high": float(row["High"]),
                      "low": float(row["Low"]), "close": float(row["Close"]),
                      "volume": float(row["Volume"]),
                      "dividend": float(row.get("Dividends", 0)),
                      "split": float(row.get("Stock Splits", 0))}
            rows.append(values)
        panel[ticker] = rows
    latest = {rows[-1]["date"] for rows in panel.values()}
    if len(latest) != 1:
        raise ValueError("Última sesión incompleta entre activos: " + str(sorted(latest)))
    asof = latest.pop()
    if asof != today:
        raise ValueError("La sesión de NYSE aún no está disponible completa: " + asof)
    return {"schema_version": 1, "asof": asof, "currency": "USD", "source": "yfinance/raw_ohlc",
            "synthetic": False,
            "captured_at_utc": now.isoformat(), "bars": panel}
