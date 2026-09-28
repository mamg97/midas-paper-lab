"""Separate one-session EUR paper portfolios for the four TFM forecast families."""

import copy
import hashlib
import json
import math


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _positive(value, label, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("Parámetro de cartera inválido: " + label)
    if maximum is not None and value > maximum:
        raise ValueError("Límite de cartera inválido: " + label)
    return float(value)


def _policy(config):
    policy = config["paper_policy"]
    for name in ("capital", "invest_fraction", "max_entry_weight", "min_predicted_return"):
        _positive(policy[name], name, 1 if name != "capital" else None)
    for name in ("commission", "slippage"):
        value = policy[name]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value < .1:
            raise ValueError("Coste inválido: " + name)
    maximum = policy["max_positions"]
    if type(maximum) is not int or not 1 <= maximum <= len(config["tickers"]):
        raise ValueError("max_positions inválido")
    return policy


def _select(predictions, policy):
    threshold = 100 * policy["min_predicted_return"]
    ranked = sorted(((ticker, values["return_predicted_pct"]) for ticker, values in predictions.items()
                     if values["return_predicted_pct"] > threshold), key=lambda row: (-row[1], row[0]))
    return [{"ticker": ticker, "predicted_return_pct": float(value)}
            for ticker, value in ranked[:policy["max_positions"]]]


def _settle(book, panel, day, pending, policy):
    if not pending:
        return
    nav_before = book["nav"]
    budget = min(nav_before * policy["max_entry_weight"],
                 nav_before * policy["invest_fraction"] / len(pending))
    spent = proceeds = 0.0
    for order in pending:
        ticker = order["ticker"]
        bar = next((bar for bar in panel[ticker] if bar["date"] == day), None)
        if bar is None:
            raise ValueError("Sin apertura/cierre para liquidar: " + ticker)
        raw_open, raw_close = bar["open"], bar["close"]
        if not all(math.isfinite(value) and value > 0 for value in (raw_open, raw_close)):
            raise ValueError("Precio de liquidación inválido")
        buy = raw_open * (1 + policy["slippage"])
        sell = raw_close * (1 - policy["slippage"])
        quantity = math.floor(budget / (buy * (1 + policy["commission"])))
        if quantity == 0:
            book.setdefault("unfilled", []).append({"signal_date": order["signal_date"], "date": day,
                                                      "ticker": ticker, "reason": "budget_below_one_share"})
            continue
        cash_out = quantity * buy * (1 + policy["commission"])
        buy_fee = quantity * buy * policy["commission"]
        sell_fee = quantity * sell * policy["commission"]
        received = quantity * sell - sell_fee
        spent += cash_out
        proceeds += received
        book["trades"].append({"signal_date": order["signal_date"], "date": day,
                               "ticker": ticker, "quantity": quantity,
                               "buy_price": buy, "sell_price": sell,
                               "buy_commission": buy_fee, "sell_commission": sell_fee,
                               "net_pnl": received - cash_out,
                               "predicted_return_pct": order["predicted_return_pct"]})
    book["nav"] = nav_before - spent + proceeds
    if not math.isfinite(book["nav"]) or book["nav"] < 0:
        raise ValueError("Contabilidad inválida")


def advance(config, panel, forecast, state=None):
    policy = _policy(config)
    asof = forecast["asof"]
    if set(forecast.get("models", {})) != set(config["models"]):
        raise ValueError("Faltan pronósticos para una cartera")
    if any(set(values) != set(config["tickers"]) for values in forecast["models"].values()):
        raise ValueError("Universo de pronósticos incompleto")
    dates = [bar["date"] for bar in next(iter(panel.values()))]
    if dates[-1] != asof:
        raise ValueError("Pronóstico y cotizaciones no comparten cierre")
    config_hash, forecast_hash = digest(config), digest(forecast)
    if state is None:
        result = {"schema_version": 1, "config_hash": config_hash, "currency": "EUR",
                  "first_session": asof, "last_session": asof, "forecast_hash": forecast_hash,
                  "missed_decision_sessions": [], "models": {}}
        for name, values in forecast["models"].items():
            result["models"][name] = {"nav": float(policy["capital"]),
                                       "pending": [{**order, "signal_date": asof}
                                                   for order in _select(values, policy)],
                                       "trades": [], "unfilled": [],
                                       "equity": [{"date": asof, "nav": float(policy["capital"]),
                                                                  "decision_recorded": True}]}
        return result, True
    if state.get("config_hash") != config_hash or set(state.get("models", {})) != set(config["models"]):
        raise ValueError("Configuración de carteras modificada")
    if state["last_session"] == asof:
        if state["forecast_hash"] != forecast_hash:
            raise ValueError("Predicción revisada para la misma sesión")
        return copy.deepcopy(state), False
    if state["last_session"] not in dates or state["last_session"] >= asof:
        raise ValueError("Sesión fuera de orden")
    next_index = dates.index(state["last_session"]) + 1
    missing = len(dates) - next_index - 1
    if missing > 5:
        raise ValueError("Demasiadas sesiones sin decisión")
    result = copy.deepcopy(state)
    settlement_day = dates[next_index]
    for name, book in result["models"].items():
        _settle(book, panel, settlement_day, book["pending"], policy)
        book["pending"] = []
        for day in dates[next_index:]:
            book["equity"].append({"date": day, "nav": book["nav"],
                                   "decision_recorded": day == asof})
        book["pending"] = [{**order, "signal_date": asof}
                           for order in _select(forecast["models"][name], policy)]
    result["missed_decision_sessions"].extend(dates[next_index:-1])
    result["last_session"] = asof
    result["forecast_hash"] = forecast_hash
    return result, True
