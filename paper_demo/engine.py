"""Stateful, close-to-next-open paper execution. No broker connectivity."""

import copy
import hashlib
import json
import math
from datetime import date

from strategies import signal


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < minimum:
        raise ValueError("Número inválido: " + label)
    return float(value)


def validate(config, snapshot):
    if config.get("schema_version") != 1 or snapshot.get("schema_version") != 1:
        raise ValueError("Versión de esquema no admitida")
    tickers = config.get("tickers")
    if not isinstance(tickers, list) or not 1 <= len(tickers) <= 30 or len(set(tickers)) != len(tickers):
        raise ValueError("Universo inválido")
    if any(not isinstance(t, str) or not t.isascii() or not t.replace("-", "").isupper() for t in tickers):
        raise ValueError("Ticker inválido")
    benchmarks = config.get("benchmark_tickers", [])
    if not isinstance(benchmarks, list) or len(set(benchmarks)) != len(benchmarks) or set(benchmarks) & set(tickers):
        raise ValueError("Benchmarks inválidos")
    if any(not isinstance(t, str) or not t.isascii() or not t.replace("-", "").isupper() for t in benchmarks):
        raise ValueError("Benchmark ticker inválido")
    market_tickers = tickers + benchmarks
    if config.get("currency") != "USD" or snapshot.get("currency") != "USD":
        raise ValueError("Esta campaña admite solamente activos en USD")
    if not isinstance(snapshot.get("source"), str) or not snapshot["source"] or type(snapshot.get("synthetic")) is not bool:
        raise ValueError("Declarar proveedor y si los datos son sintéticos")
    for key, minimum, maximum in (("capital", 1, None), ("commission", 0, .1),
                                  ("slippage", 0, .1), ("invest_fraction", .000001, 1),
                                  ("max_entry_weight", .000001, 1)):
        value = _number(config.get(key), key, minimum)
        if maximum is not None and value > maximum:
            raise ValueError("Límite inválido: " + key)
    limit = config.get("max_positions")
    if type(limit) is not int or not 1 <= limit <= len(tickers):
        raise ValueError("max_positions inválido")
    missed_limit = config.get("max_missed_sessions", 0)
    if type(missed_limit) is not int or not 0 <= missed_limit <= 10:
        raise ValueError("max_missed_sessions inválido")
    specs = config.get("strategies")
    if not isinstance(specs, dict) or not specs:
        raise ValueError("Sin estrategias")
    for name, spec in specs.items():
        if not isinstance(name, str) or not name or not isinstance(spec, dict):
            raise ValueError("Estrategia inválida")
        if spec.get("kind") == "genetic_frozen" and not spec.get("params"):
            continue
        if spec.get("kind") not in ("equal_weight_hold", "ema_rsi", "genetic_frozen", "macd",
                                    "rsi_reversion", "bollinger_breakout", "turtle_20_10", "turtle_55_20"):
            raise ValueError("Tipo de estrategia desconocido: " + str(spec.get("kind")))
        for field in ("stop_loss", "take_profit"):
            if spec.get(field) is not None and not 0 < _number(spec[field], field) < 1:
                raise ValueError("Control de salida inválido")
        universe = spec.get("universe", tickers)
        if not isinstance(universe, list) or not universe or len(set(universe)) != len(universe) or not set(universe) <= set(market_tickers):
            raise ValueError("Universo de estrategia inválido")
        if set(universe) & set(benchmarks) and spec.get("kind") != "equal_weight_hold":
            raise ValueError("Benchmark reservado para compra y mantenimiento")
        weight = spec.get("entry_weight", config["max_entry_weight"])
        if not 0 < _number(weight, "entry_weight") <= 1:
            raise ValueError("Peso de entrada inválido")
        if spec["kind"] in ("ema_rsi", "genetic_frozen"):
            p = spec.get("params") or {}
            if (type(p.get("fast")) is not int or type(p.get("slow")) is not int or
                    type(p.get("rsi_period")) is not int or not 2 <= p["fast"] < p["slow"] <= 250 or
                    not 2 <= p["rsi_period"] <= 100 or not 0 <= p.get("oversold", -1) < p.get("overbought", 101) <= 100):
                raise ValueError("Genoma inválido")
    asof = snapshot.get("asof")
    try:
        if date.fromisoformat(asof).isoformat() != asof:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("Fecha asof inválida")
    panel = snapshot.get("bars")
    if not isinstance(panel, dict) or set(panel) != set(market_tickers):
        raise ValueError("Datos incompletos del universo")
    common_dates = None
    for ticker in market_tickers:
        rows = panel[ticker]
        if not isinstance(rows, list) or len(rows) < 80:
            raise ValueError("Historial insuficiente: " + ticker)
        dates = []
        for bar in rows:
            try:
                day = date.fromisoformat(bar["date"]).isoformat()
            except (KeyError, TypeError, ValueError):
                raise ValueError("Barra sin fecha válida: " + ticker)
            dates.append(day)
            for field in ("open", "high", "low", "close"):
                _number(bar.get(field), field, .0000001)
            _number(bar.get("volume"), "volume")
            _number(bar.get("dividend", 0), "dividend")
            _number(bar.get("split", 0), "split")
            if not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]:
                raise ValueError("OHLC incoherente: " + ticker + " " + day)
        if dates != sorted(set(dates)) or dates[-1] != asof:
            raise ValueError("Fechas desordenadas o última sesión incorrecta: " + ticker)
        if common_dates is None:
            common_dates = dates
        elif dates != common_dates:
            raise ValueError("Calendarios incompletos o distintos")
    return common_dates


def _event(portfolio, kind, asof, ticker=None, **fields):
    portfolio["events"].append({"type": kind, "date": asof, "ticker": ticker, **fields})


def _sell(portfolio, ticker, bar, config, asof, reason, signal_date=None, reference=None):
    position = portfolio["positions"].pop(ticker)
    price = (bar["open"] if reference is None else reference) * (1 - config["slippage"])
    gross = position["quantity"] * price
    fee = gross * config["commission"]
    portfolio["cash"] += gross - fee
    _event(portfolio, "fill", asof, ticker, side="sell", quantity=position["quantity"],
           price=price, fee=fee, reason=reason, signal_date=signal_date)


def _settle(portfolio, spec, config, snapshot):
    asof = snapshot["asof"]
    current = {t: snapshot["bars"][t][-1] for t in config["tickers"] + config.get("benchmark_tickers", [])}
    # Corporate actions take effect before this session's opening trades.
    for ticker, position in sorted(portfolio["positions"].items()):
        bar = current[ticker]
        split = bar.get("split", 0)
        if split:
            position["quantity"] *= split
            for field in ("entry_price", "stop", "target"):
                if position[field] is not None:
                    position[field] /= split
            _event(portfolio, "split", asof, ticker, ratio=split)
        dividend = bar.get("dividend", 0)
        if dividend:
            amount = dividend * position["quantity"]
            portfolio["cash"] += amount
            _event(portfolio, "dividend", asof, ticker, amount=amount, per_share=dividend)
    stopped = set()
    for ticker in sorted(list(portfolio["positions"])):
        bar, position = current[ticker], portfolio["positions"][ticker]
        queued = portfolio["pending"].get(ticker)
        if position["stop"] is not None and bar["open"] <= position["stop"]:
            _sell(portfolio, ticker, bar, config, asof, "stop_gap")
            stopped.add(ticker)
        elif position["target"] is not None and bar["open"] >= position["target"]:
            _sell(portfolio, ticker, bar, config, asof, "target_gap")
            stopped.add(ticker)
        elif queued and queued["side"] == "sell":
            _sell(portfolio, ticker, bar, config, asof, "close_signal", queued["signal_date"])
    entrants = sorted(t for t, order in portfolio["pending"].items()
                      if order["side"] == "buy" and t not in portfolio["positions"] and t not in stopped)
    slots = config["max_positions"] - len(portfolio["positions"])
    for ticker in entrants[slots:]:
        _event(portfolio, "skip", asof, ticker, reason="max_positions")
    entrants = entrants[:slots]
    open_nav = portfolio["cash"] + sum(p["quantity"] * current[t]["open"] for t, p in portfolio["positions"].items())
    budget = min(open_nav * spec.get("entry_weight", config["max_entry_weight"]),
                 portfolio["cash"] * config["invest_fraction"] / len(entrants)) if entrants else 0
    for ticker in entrants:
        if budget <= 0:
            _event(portfolio, "skip", asof, ticker, reason="no_cash")
            continue
        price = current[ticker]["open"] * (1 + config["slippage"])
        quantity = budget / (price * (1 + config["commission"]))
        fee = quantity * price * config["commission"]
        portfolio["cash"] -= quantity * price + fee
        portfolio["positions"][ticker] = {
            "quantity": quantity, "entry_price": price,
            "stop": price * (1 - spec["stop_loss"]) if spec.get("stop_loss") else None,
            "target": price * (1 + spec["take_profit"]) if spec.get("take_profit") else None,
        }
        _event(portfolio, "fill", asof, ticker, side="buy", quantity=quantity, price=price,
               fee=fee, reason="close_signal", signal_date=portfolio["pending"][ticker]["signal_date"])
    portfolio["pending"] = {}
    # If both barriers are inside one OHLC candle, assume the adverse stop first.
    for ticker in sorted(list(portfolio["positions"])):
        bar, position = current[ticker], portfolio["positions"][ticker]
        if position["stop"] is not None and bar["low"] <= position["stop"]:
            _sell(portfolio, ticker, bar, config, asof, "stop_intraday", reference=position["stop"])
        elif position["target"] is not None and bar["high"] >= position["target"]:
            _sell(portfolio, ticker, bar, config, asof, "target_intraday", reference=position["target"])


def advance(config, snapshot, state=None):
    dates = validate(config, snapshot)
    asof = snapshot["asof"]
    market_hash = digest({"asof": asof, "bars": snapshot["bars"], "source": snapshot.get("source")})
    config_hash = digest(config)
    if state is None:
        result = {"schema_version": 1, "config_hash": config_hash, "first_session": asof,
                  "last_session": None, "source": snapshot["source"],
                  "synthetic": snapshot["synthetic"], "market_hashes": {},
                  "missed_decision_sessions": [], "strategies": {}}
        for name, spec in config["strategies"].items():
            result["strategies"][name] = {"status": "waiting_for_model" if spec["kind"] == "genetic_frozen" and not spec.get("params") else "active",
                                          "cash": float(config["capital"]), "positions": {}, "pending": {}, "events": [], "equity": []}
    else:
        if state.get("config_hash") != config_hash or set(state.get("strategies", {})) != set(config["strategies"]):
            raise ValueError("Configuración modificada: iniciar otra campaña")
        if state.get("source") != snapshot["source"] or state.get("synthetic") != snapshot["synthetic"]:
            raise ValueError("Proveedor o naturaleza de datos cambiados")
        if state.get("last_session") == asof:
            if state["market_hashes"][asof] != market_hash:
                raise ValueError("Datos revisados para una sesión ya registrada")
            return copy.deepcopy(state), False
        if not state.get("last_session") or state["last_session"] >= asof or state["last_session"] not in dates:
            raise ValueError("Sesión fuera de orden o fuera del historial descargado")
        result = copy.deepcopy(state)
    first_index = len(dates) - 1 if state is None else dates.index(state["last_session"]) + 1
    if len(dates) - first_index - 1 > config.get("max_missed_sessions", 0):
        raise ValueError("Demasiadas sesiones sin decisión; revisar antes de continuar")
    for index in range(first_index, len(dates)):
        day = dates[index]
        is_current = day == asof
        daily_snapshot = {"asof": day, "bars": {ticker: [rows[index]] for ticker, rows in snapshot["bars"].items()}}
        if not is_current:
            result["missed_decision_sessions"].append(day)
        for name, spec in config["strategies"].items():
            portfolio = result["strategies"][name]
            if portfolio["status"] == "active":
                if state is not None:
                    _settle(portfolio, spec, config, daily_snapshot)
                if is_current:
                    for ticker in spec.get("universe", config["tickers"]):
                        action = signal(spec["kind"], snapshot["bars"][ticker], spec.get("params") or {})
                        if action == "buy" and ticker not in portfolio["positions"]:
                            portfolio["pending"][ticker] = {"side": "buy", "signal_date": day}
                        elif action == "sell" and ticker in portfolio["positions"]:
                            portfolio["pending"][ticker] = {"side": "sell", "signal_date": day}
                        if action != "hold":
                            _event(portfolio, "signal", day, ticker, side=action)
                else:
                    _event(portfolio, "decision_missed", day, recorded_at=asof)
            nav = portfolio["cash"] + sum(position["quantity"] * daily_snapshot["bars"][ticker][-1]["close"]
                                          for ticker, position in portfolio["positions"].items())
            if not math.isfinite(nav) or nav < 0 or portfolio["cash"] < -1e-7:
                raise ValueError("Contabilidad no válida: " + name)
            portfolio["equity"].append({"date": day, "nav": nav, "cash": portfolio["cash"],
                                         "decision_recorded": is_current})
    result["last_session"] = asof
    result["market_hashes"][asof] = market_hash
    return result, True


def leaderboard(config, state):
    output = []
    for name, portfolio in state["strategies"].items():
        high = config["capital"]
        drawdown = 0
        for row in portfolio["equity"]:
            high = max(high, row["nav"])
            drawdown = max(drawdown, 1 - row["nav"] / high)
        nav = portfolio["equity"][-1]["nav"]
        output.append({"strategy": name, "status": portfolio["status"], "first_session": state["first_session"],
                       "last_session": state["last_session"], "nav": nav,
                       "return_pct": 100 * (nav / config["capital"] - 1),
                       "max_drawdown_pct": 100 * drawdown,
                       "missed_decisions": len(state.get("missed_decision_sessions", [])),
                       "positions": len(portfolio["positions"]),
                       "fills": sum(e["type"] == "fill" for e in portfolio["events"])})
    return sorted(output, key=lambda row: (row["status"] != "active", -row["return_pct"], row["strategy"]))
