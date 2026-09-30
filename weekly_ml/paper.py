"""Prospective weekly paper accounting for MIDAS ML experts."""

import copy
import hashlib
import json
import math

from data import execution_window


BENCHMARKS = {"benchmark_spy": "SPY", "benchmark_rsp": "RSP"}


def _fractional_quantity(budget, buy_price, policy):
    if not policy.get("fractional_shares", False):
        return float(math.floor(budget / (buy_price * (1 + float(policy["commission"])))))
    precision = int(policy.get("share_precision", 6))
    if not 0 <= precision <= 8:
        raise ValueError("share_precision inválido")
    minimum = float(policy.get("min_notional", 0))
    raw = budget / (buy_price * (1 + float(policy["commission"])))
    scale = 10 ** precision
    quantity = math.floor(raw * scale) / scale
    if quantity <= 0 or quantity * buy_price < minimum:
        return 0.0
    return quantity


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def strategy_ids(config):
    return list(config["models"]) + list(BENCHMARKS)


def _select(model, predictions, policy, asof):
    if model in BENCHMARKS:
        return [{"ticker": BENCHMARKS[model], "signal_date": asof, "score": 1.0}]
    rows = []
    if model == "lgbm_direction":
        for ticker, value in predictions.items():
            probability = float(value["direction_probability"])
            if probability >= policy["min_direction_probability"]:
                rows.append({"ticker": ticker, "signal_date": asof, "score": probability,
                             "direction_probability": probability})
    elif model == "lgbm_ranker":
        for ticker, value in predictions.items():
            rows.append({"ticker": ticker, "signal_date": asof, "score": float(value["rank_score"])})
    elif model == "ensemble_consensus":
        for ticker, value in predictions.items():
            if (int(value["positive_votes"]) >= int(policy["ensemble_min_positive_votes"])
                    and float(value["predicted_return"]) >= float(policy["min_predicted_return"])):
                rows.append({"ticker": ticker, "signal_date": asof,
                             "score": float(value["score"]),
                             "predicted_return": float(value["predicted_return"]),
                             "positive_votes": int(value["positive_votes"]),
                             "rank_dispersion": float(value["rank_dispersion"])})
    else:
        for ticker, value in predictions.items():
            predicted = float(value["predicted_return"])
            if predicted >= float(policy["min_predicted_return"]):
                rows.append({"ticker": ticker, "signal_date": asof, "score": predicted,
                             "predicted_return": predicted})
    rows.sort(key=lambda x: (-x["score"], x["ticker"]))
    return rows[: int(policy["max_positions"])]


def _settle(book, panel, current_asof, pending, policy, benchmark=False):
    if not pending:
        return []
    nav_before = float(book["nav"])
    if benchmark:
        budget_each = nav_before * float(policy["invest_fraction"])
    else:
        budget_each = min(
            nav_before * float(policy["max_entry_weight"]),
            nav_before * float(policy["invest_fraction"]) / len(pending),
        )
    trades = []
    for order in pending:
        ticker = order["ticker"]
        window = execution_window(panel, ticker, order["signal_date"])
        if window is None or window["last_session"] > current_asof:
            raise ValueError("Aún no existe una semana completa para liquidar: " + ticker)
        raw_open = float(window["open"])
        raw_close = float(window["close"])
        buy = raw_open * (1 + float(policy["slippage"]))
        sell = raw_close * (1 - float(policy["slippage"]))
        quantity = _fractional_quantity(budget_each, buy, policy)
        if quantity <= 0:
            book.setdefault("unfilled", []).append({
                "signal_date": order["signal_date"], "ticker": ticker,
                "reason": "below_min_notional", **window,
            })
            continue
        buy_fee = quantity * buy * float(policy["commission"])
        sell_fee = quantity * sell * float(policy["commission"])
        cash_out = quantity * buy + buy_fee
        received = quantity * sell - sell_fee
        trade = {
            **order,
            **window,
            "quantity": quantity,
            "buy_price": buy,
            "sell_price": sell,
            "buy_commission": buy_fee,
            "sell_commission": sell_fee,
            "net_pnl": received - cash_out,
            "gross_return_pct": 100 * (raw_close / raw_open - 1),
            "net_return_pct": 100 * (received / cash_out - 1),
        }
        trades.append(trade)
        book["nav"] += received - cash_out
    if not math.isfinite(book["nav"]) or book["nav"] < 0:
        raise ValueError("NAV semanal inválido")
    book["trades"].extend(trades)
    return trades


def advance(config, panel, forecast, state=None):
    policy = config["paper_policy"]
    asof = forecast["asof"]
    strategies = strategy_ids(config)
    config_hash = digest(config)
    forecast_hash = digest(forecast)

    if set(forecast["models"]) != set(config["models"]):
        raise ValueError("El forecast semanal no contiene todos los modelos")

    if state is None:
        state = {
            "schema_version": 1,
            "config_hash": config_hash,
            "currency": config["currency"],
            "first_session": asof,
            "last_session": asof,
            "forecast_hash": forecast_hash,
            "missed_signal_weeks": [],
            "execution": {
                "fractional_shares": bool(policy.get("fractional_shares", False)),
                "share_precision": int(policy.get("share_precision", 0)),
                "min_notional": float(policy.get("min_notional", 0)),
            },
            "strategies": {},
        }
        for name in strategies:
            predictions = forecast["models"].get(name, {})
            pending = _select(name, predictions, policy, asof)
            state["strategies"][name] = {
                "nav": float(policy["capital"]),
                "pending": pending,
                "trades": [],
                "unfilled": [],
                "equity": [{"date": asof, "nav": float(policy["capital"]),
                            "decision_recorded": True}],
            }
        return state, True

    if state.get("config_hash") != config_hash:
        raise ValueError("Configuración semanal modificada: iniciar campaña nueva")
    if set(state.get("strategies", {})) != set(strategies):
        raise ValueError("Faltan carteras semanales")
    if state["last_session"] == asof:
        if state.get("forecast_hash") != forecast_hash:
            raise ValueError("Forecast semanal revisado para la misma fecha")
        return copy.deepcopy(state), False
    if state["last_session"] > asof:
        raise ValueError("Sesión semanal fuera de orden")

    result = copy.deepcopy(state)
    previous_session = state["last_session"]
    for name, book in result["strategies"].items():
        _settle(book, panel, asof, book["pending"], policy, benchmark=name in BENCHMARKS)
        predictions = forecast["models"].get(name, {})
        book["pending"] = _select(name, predictions, policy, asof)
        book["equity"].append({"date": asof, "nav": float(book["nav"]),
                               "decision_recorded": True})

    # If more than one calendar week elapsed, do not manufacture signals for missing weeks.
    from datetime import date
    elapsed = (date.fromisoformat(asof) - date.fromisoformat(previous_session)).days
    if elapsed > 10:
        result["missed_signal_weeks"].append({
            "after": previous_session, "before": asof,
            "note": "No se crean señales retroactivas para semanas omitidas.",
        })
    result["last_session"] = asof
    result["forecast_hash"] = forecast_hash
    return result, True
