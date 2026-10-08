"""Expose every MIDAS idea without presenting missing strategies as live results."""

import argparse
import hashlib
import json
import math
import os
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _read(path, *, optional=False):
    path = Path(path)
    if optional and not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _config_hash(config):
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _equity(value, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError("Patrimonio inválido: " + label)
    return float(value)


def _daily_return(history, label):
    if len(history) < 2:
        return None
    previous = _equity(history[-2].get("nav"), label + " anterior")
    current = _equity(history[-1].get("nav"), label)
    if previous == 0:
        return None
    return round(100 * (current / previous - 1), 6)


def _equity_history(history, label, limit=520):
    if not isinstance(history, list):
        return []
    points = []
    for item in history[-limit:]:
        if not isinstance(item, dict):
            raise ValueError("Histórico de patrimonio inválido: " + label)
        date = item.get("date")
        nav = _equity(item.get("nav"), label + " histórico")
        if not isinstance(date, str) or len(date) < 10:
            raise ValueError("Fecha de patrimonio inválida: " + label)
        points.append({"date": date[:10], "nav": nav})
    if any(points[index]["date"] <= points[index - 1]["date"] for index in range(1, len(points))):
        raise ValueError("Histórico de patrimonio desordenado: " + label)
    return points


def _risk_metrics(points):
    """Risk from the same recorded NAV path shown in the dashboard."""
    if not isinstance(points, list) or not points:
        return {
            "risk_observations": 0,
            "annualized_volatility_pct": None,
            "max_drawdown_pct": None,
            "sharpe_0rf": None,
        }
    navs = [float(point["nav"]) for point in points if isinstance(point, dict) and _equity(point.get("nav"), "riesgo") >= 0]
    if not navs:
        return {
            "risk_observations": 0,
            "annualized_volatility_pct": None,
            "max_drawdown_pct": None,
            "sharpe_0rf": None,
        }
    peak = navs[0]
    max_dd = 0.0
    for nav in navs:
        peak = max(peak, nav)
        if peak > 0:
            max_dd = min(max_dd, nav / peak - 1.0)

    returns = []
    dates = []
    for index, point in enumerate(points):
        try:
            dates.append(datetime.fromisoformat(str(point["date"])[:10]).date())
        except (TypeError, ValueError, KeyError):
            dates.append(None)
        if index and navs[index - 1] > 0:
            returns.append(navs[index] / navs[index - 1] - 1.0)

    volatility = sharpe = None
    # Annualized volatility and Sharpe are too unstable with only a handful of
    # observations. Keep max drawdown from day one, but wait for 10 returns.
    if len(returns) >= 10:
        sd = statistics.stdev(returns)
        valid_gaps = [
            (dates[i] - dates[i - 1]).days
            for i in range(1, len(dates))
            if dates[i] is not None and dates[i - 1] is not None and (dates[i] - dates[i - 1]).days > 0
        ]
        gap = statistics.median(valid_gaps) if valid_gaps else 1
        periods = 252.0 if gap <= 3 else 52.0 if gap <= 10 else 12.0 if gap <= 40 else 4.0
        volatility = 100.0 * sd * math.sqrt(periods)
        if sd > 1e-15:
            sharpe = statistics.fmean(returns) / sd * math.sqrt(periods)

    return {
        "risk_observations": len(navs),
        "annualized_volatility_pct": None if volatility is None else round(volatility, 6),
        "max_drawdown_pct": round(100.0 * max_dd, 6),
        "sharpe_0rf": None if sharpe is None else round(sharpe, 6),
    }


TFM_IDS = {"tfm_lgbm_2023": "lgbm", "tfm_mlp_2023": "mlp",
           "tfm_lstm_2023": "lstm", "tfm_arima_2023": "arima"}


def _activity_tickers(value):
    if isinstance(value, dict):
        return [str(ticker) for ticker in value if ticker]
    if isinstance(value, list):
        return [str(item.get("ticker")) for item in value
                if isinstance(item, dict) and item.get("ticker")]
    return []


def _activity(positions=None, pending=None, *, pending_label="órdenes pendientes",
              empty_label="Sin compras · en efectivo"):
    position_tickers = _activity_tickers(positions)
    pending_tickers = _activity_tickers(pending)
    combined = []
    for ticker in position_tickers + pending_tickers:
        if ticker not in combined:
            combined.append(ticker)
    open_count = len(position_tickers)
    pending_count = len(pending_tickers)
    if open_count and pending_count:
        state = "active_pending"
        label = f"{open_count} posiciones · {pending_count} {pending_label}"
    elif open_count:
        state = "active"
        label = f"{open_count} " + ("posición abierta" if open_count == 1 else "posiciones abiertas")
    elif pending_count:
        state = "pending"
        label = f"{pending_count} {pending_label}"
    else:
        state = "cash"
        label = empty_label
    return {
        "activity_state": state,
        "activity_label": label,
        "activity_tickers": combined[:12],
        "open_positions_count": open_count,
        "pending_orders_count": pending_count,
    }


def build(registry, paper_config, paper_state=None, legacy_state=None, now=None,
          tfm_config=None, tfm_state=None, weekly_config=None, weekly_state=None,
          tfg_config=None, tfg_state=None, capital_config=None, capital_state=None,
          btd_config=None, btd_state=None):
    if registry.get("schema_version") != 1:
        raise ValueError("Versión de registro no válida")
    paper_names = registry.get("paper_tracks", {})
    if not isinstance(paper_names, dict) or set(paper_names) != set(paper_config.get("strategies", {})):
        raise ValueError("Registro y configuración paper no coinciden")
    ideas = registry.get("historical_ideas", [])
    legacy_tracks = registry.get("legacy_tracks", [])
    weekly_tracks = registry.get("weekly_ml_tracks", {})
    if not isinstance(weekly_tracks, dict):
        raise ValueError("Registro weekly ML inválido")
    weekly_ids = [item["id"] for item in weekly_tracks.values()]
    tfg_tracks = registry.get("tfg_tracks", {})
    if not isinstance(tfg_tracks, dict):
        raise ValueError("Registro TFG inválido")
    tfg_ids = [item["id"] for item in tfg_tracks.values()]
    capital_tracks = registry.get("capital_cycle_tracks", {})
    if not isinstance(capital_tracks, dict):
        raise ValueError("Registro Capital Cycle inválido")
    capital_ids = [item["id"] for item in capital_tracks.values()]
    btd_tracks = registry.get("buy_the_dip_tracks", {})
    if not isinstance(btd_tracks, dict):
        raise ValueError("Registro Buy The Dip inválido")
    btd_ids = [item["id"] for item in btd_tracks.values()]
    ids = list(paper_names) + weekly_ids + tfg_ids + capital_ids + btd_ids + [x["id"] for x in legacy_tracks + ideas]
    if len(ids) != len(set(ids)):
        raise ValueError("Ideas duplicadas")
    provenance = registry.get("provenance", {})
    if set(provenance) != set(ids) or not all(isinstance(value, str) and value.strip() for value in provenance.values()):
        raise ValueError("Procedencia incompleta o inválida")
    capital = _equity(paper_config.get("capital"), "capital inicial paper")
    if capital == 0:
        raise ValueError("Capital paper cero")
    if paper_state is not None:
        if paper_state.get("config_hash") != _config_hash(paper_config):
            raise ValueError("El diario paper pertenece a otra configuración")
        if set(paper_state.get("strategies", {})) != set(paper_names):
            raise ValueError("Faltan carteras paper")
    if tfm_config is not None:
        if set(tfm_config.get("models", [])) != set(TFM_IDS.values()):
            raise ValueError("Configuración TFM incompleta")
        if not TFM_IDS.keys() <= {item["id"] for item in ideas}:
            raise ValueError("El catálogo omite variantes TFM")
    if tfm_state is not None:
        if tfm_config is None or tfm_state.get("config_hash") != _config_hash(tfm_config):
            raise ValueError("El diario TFM pertenece a otra configuración")
        if set(tfm_state.get("models", {})) != set(TFM_IDS.values()):
            raise ValueError("Faltan carteras TFM")
    if weekly_config is not None:
        expected_weekly = set(weekly_config.get("models", [])) | {"benchmark_spy", "benchmark_rsp"}
        if set(weekly_tracks) != expected_weekly:
            raise ValueError("Registro y configuración weekly ML no coinciden")
    if weekly_state is not None:
        if weekly_config is None or weekly_state.get("config_hash") != _config_hash(weekly_config):
            raise ValueError("El diario weekly ML pertenece a otra configuración")
        if set(weekly_state.get("strategies", {})) != set(weekly_tracks):
            raise ValueError("Faltan carteras weekly ML")
    if tfg_config is not None:
        if set(tfg_tracks) != {"tfg_corrected"}:
            raise ValueError("Registro TFG corregido incompleto")
        if tfg_config.get("name") != "TFG_2021_corrected_2026":
            raise ValueError("Configuración TFG no reconocida")
    if tfg_state is not None:
        if tfg_config is None or tfg_state.get("config_hash") != _config_hash(tfg_config):
            raise ValueError("El diario TFG pertenece a otra configuración")
        if not isinstance(tfg_state.get("equity"), list) or not tfg_state["equity"]:
            raise ValueError("Diario TFG sin patrimonio")
    if capital_config is not None:
        if set(capital_tracks) != {"capital_cycle_inflection"}:
            raise ValueError("Registro Capital Cycle incompleto")
        if capital_config.get("name") != "MIDAS_capital_cycle_inflection_2026":
            raise ValueError("Configuración Capital Cycle no reconocida")
    if capital_state is not None:
        if capital_config is None or capital_state.get("config_hash") != _config_hash(capital_config):
            raise ValueError("El diario Capital Cycle pertenece a otra configuración")
        if capital_state.get("strategy_id") != "capital_cycle_inflection_2026":
            raise ValueError("Diario Capital Cycle no reconocido")
        if not isinstance(capital_state.get("equity"), list) or not capital_state["equity"]:
            raise ValueError("Diario Capital Cycle sin patrimonio")
    if btd_config is not None:
        if set(btd_tracks) != {"buy_the_dip_corpus"}:
            raise ValueError("Registro Buy The Dip incompleto")
        if btd_config.get("name") != "MIDAS_buy_the_dip_corpus_v0_2026":
            raise ValueError("Configuración Buy The Dip no reconocida")
    if btd_state is not None:
        if btd_config is None or btd_state.get("config_hash") != _config_hash(btd_config):
            raise ValueError("El diario Buy The Dip pertenece a otra configuración")
        if btd_state.get("strategy_id") != "buy_the_dip_corpus_2026_v0":
            raise ValueError("Diario Buy The Dip no reconocido")
        if not isinstance(btd_state.get("equity"), list) or not btd_state["equity"]:
            raise ValueError("Diario Buy The Dip sin patrimonio")
    timestamp = now or datetime.now(timezone.utc)
    rows = []
    for strategy_id, label in paper_names.items():
        row = {"id": strategy_id, "label": label, "provenance": provenance[strategy_id],
               "group": "paper_nuevo", "status": "programada_sin_diario",
               "first_session": None, "last_session": None, "initial_capital": capital, "last_equity": None,
               "return_pct": None, "day_return_pct": None, "currency": paper_config.get("currency", "USD"),
               "equity_history": [], "note": "Mismas reglas de contabilidad; variante nueva si el nombre indica adaptación."}
        if paper_state is not None:
            book = paper_state["strategies"][strategy_id]
            history = book.get("equity", [])
            if not history:
                raise ValueError("Cartera sin patrimonio: " + strategy_id)
            nav = _equity(history[-1].get("nav"), strategy_id)
            row.update(status="demo_con_diario" if book.get("status") == "active" else "pendiente_modelo",
                       first_session=paper_state.get("first_session"),
                       last_session=paper_state.get("last_session"), last_equity=nav,
                       return_pct=round(100 * (nav / capital - 1), 6),
                       day_return_pct=_daily_return(history, strategy_id),
                       equity_history=_equity_history(history, strategy_id))
            row.update(_activity(book.get("positions"), book.get("pending")))
        rows.append(row)
    for strategy_key, item in weekly_tracks.items():
        capital_weekly = None if weekly_config is None else _equity(
            weekly_config["paper_policy"]["capital"], "capital weekly ML")
        row = {"id": item["id"], "label": item["label"], "provenance": provenance[item["id"]],
               "group": "weekly_ml_demo", "status": "programada_sin_diario",
               "first_session": None, "last_session": None,
               "initial_capital": capital_weekly, "last_equity": None,
               "return_pct": None, "day_return_pct": None,
               "currency": None if weekly_config is None else weekly_config.get("currency", "USD"),
               "equity_history": [],
               "note": "Señales congeladas al cierre semanal. El motor actual no registra fills ni NAV diarios: simula entrada en la siguiente primera apertura y salida al último cierre semanal al procesar el viernes siguiente. Una señal pendiente NO es una compra ejecutada."}
        if weekly_state is not None:
            book = weekly_state["strategies"][strategy_key]
            history = book.get("equity", [])
            if not history:
                raise ValueError("Cartera weekly ML sin patrimonio: " + strategy_key)
            nav = _equity(history[-1].get("nav"), strategy_key)
            if history[-1].get("date") != weekly_state.get("last_session"):
                raise ValueError("Patrimonio weekly ML sin fecha válida")
            row.update(status="demo_con_diario",
                       first_session=weekly_state.get("first_session"),
                       last_session=weekly_state.get("last_session"),
                       last_equity=nav,
                       return_pct=round(100 * (nav / capital_weekly - 1), 6),
                       day_return_pct=_daily_return(history, strategy_key),
                       equity_history=_equity_history(history, strategy_key))
            row.update(_activity(None, book.get("pending"),
                                 pending_label="señales congeladas · liquidación semanal pendiente"))
        rows.append(row)
    for strategy_key, item in tfg_tracks.items():
        capital_tfg = None if tfg_config is None else _equity(
            tfg_config["portfolio"]["capital"], "capital TFG")
        row = {"id": item["id"], "label": item["label"], "provenance": provenance[item["id"]],
               "group": "tfg_demo_adaptado", "status": "programada_sin_diario",
               "first_session": None, "last_session": None,
               "initial_capital": capital_tfg, "last_equity": None,
               "return_pct": None, "day_return_pct": None,
               "currency": None if tfg_config is None else tfg_config.get("currency", "USD"),
               "equity_history": [],
               "note": "Arquitectura TFG 2021 portada con riesgo/beta sobre retornos y ejecución prospectiva next-open."}
        if tfg_state is not None:
            history = tfg_state["equity"]
            nav = _equity(tfg_state.get("nav"), item["id"])
            if history[-1].get("date") != tfg_state.get("last_signal_session"):
                raise ValueError("Patrimonio TFG sin fecha válida")
            row.update(status="demo_con_diario",
                       first_session=tfg_state.get("first_signal_session"),
                       last_session=tfg_state.get("last_signal_session"),
                       last_equity=nav,
                       return_pct=round(100 * (nav / capital_tfg - 1), 6),
                       day_return_pct=_daily_return(history, item["id"]),
                       equity_history=_equity_history(history, item["id"]))
            signal = tfg_state.get("pending_signal")
            selections = signal.get("selections", []) if isinstance(signal, dict) else []
            row.update(_activity(None, selections,
                                 pending_label="compras para próxima apertura",
                                 empty_label="Sin compras · esperando señal"))
        rows.append(row)
    for strategy_key, item in capital_tracks.items():
        capital_cc = None if capital_config is None else _equity(
            capital_config["paper_policy"]["capital"], "capital Capital Cycle")
        row = {"id": item["id"], "label": item["label"], "provenance": provenance[item["id"]],
               "group": "capital_cycle_demo", "status": "programada_sin_diario",
               "first_session": None, "last_session": None,
               "initial_capital": capital_cc, "last_equity": None,
               "return_pct": None, "day_return_pct": None,
               "currency": None if capital_config is None else capital_config.get("currency", "USD"),
               "equity_history": [],
               "note": "Capital Cycle v1: underinvestment multianual + calidad + valoración normalizada + confirmación 6/12 meses; rebalance mensual y fills next-open."}
        if capital_state is not None:
            history = capital_state["equity"]
            nav = _equity(capital_state.get("nav"), item["id"])
            if history[-1].get("date") != capital_state.get("last_session"):
                raise ValueError("Patrimonio Capital Cycle sin fecha válida")
            row.update(status="demo_con_diario",
                       first_session=capital_state.get("first_session"),
                       last_session=capital_state.get("last_session"),
                       last_equity=nav,
                       return_pct=round(100 * (nav / capital_cc - 1), 6),
                       day_return_pct=_daily_return(history, item["id"]),
                       equity_history=_equity_history(history, item["id"]))
            row.update(_activity(capital_state.get("positions"), capital_state.get("pending")))
        rows.append(row)
    for strategy_key, item in btd_tracks.items():
        capital_btd = None if btd_config is None else _equity(
            btd_config["paper_policy"]["capital"], "capital Buy The Dip")
        row = {"id": item["id"], "label": item["label"], "provenance": provenance[item["id"]],
               "group": "buy_the_dip_demo", "status": "programada_sin_diario",
               "first_session": None, "last_session": None,
               "initial_capital": capital_btd, "last_equity": None,
               "return_pct": None, "day_return_pct": None,
               "currency": None if btd_config is None else btd_config.get("currency", "USD"),
               "equity_history": [],
               "note": "Buy The Dip corpus v0: deep value + special situations; valoración, calidad, capital allocation, dislocación y catalizadores; decisión mensual y fills next-open."}
        if btd_state is not None:
            history = btd_state["equity"]
            nav = _equity(btd_state.get("nav"), item["id"])
            if history[-1].get("date") != btd_state.get("last_session"):
                raise ValueError("Patrimonio Buy The Dip sin fecha válida")
            row.update(status="demo_con_diario",
                       first_session=btd_state.get("first_session"),
                       last_session=btd_state.get("last_session"),
                       last_equity=nav,
                       return_pct=round(100 * (nav / capital_btd - 1), 6),
                       day_return_pct=_daily_return(history, item["id"]),
                       equity_history=_equity_history(history, item["id"]))
            row.update(_activity(btd_state.get("positions"), btd_state.get("pending")))
        rows.append(row)
    for item in legacy_tracks:
        row = {"id": item["id"], "label": item["label"], "provenance": provenance[item["id"]],
               "group": "diario_heredado",
               "status": "sin_diario_disponible", "first_session": None, "last_session": None,
               "initial_capital": None, "last_equity": None, "return_pct": None,
               "day_return_pct": None, "currency": None, "equity_history": [],
               "note": item["note"]}
        if item["id"] == "genetic_sp500_legacy" and legacy_state is not None:
            history = legacy_state.get("equity_history")
            if not isinstance(history, dict) or not history:
                raise ValueError("Diario genético sin patrimonio fechado")
            dates = sorted(history)
            initial = _equity(legacy_state.get("initial_capital"), "capital genético")
            if initial == 0:
                raise ValueError("Capital genético cero")
            nav = _equity(history[dates[-1]], "patrimonio genético")
            row.update(status="diario_heredado_observado", first_session=dates[0], last_session=dates[-1],
                       initial_capital=initial, last_equity=nav,
                       return_pct=round(100 * (nav / initial - 1), 6),
                       equity_history=[{"date": date[:10], "nav": _equity(history[date], "patrimonio genético histórico")}
                                       for date in dates[-520:]])
        rows.append(row)
    for item in ideas:
        if item["id"] in TFM_IDS and tfm_config is not None:
            row = {"id": item["id"], "label": item["label"] + " (versión corregida 2026)",
                   "provenance": provenance[item["id"]],
                   "group": "tfm_demo_adaptado", "status": "programada_sin_diario",
                   "first_session": None, "last_session": None,
                   "initial_capital": _equity(tfm_config["paper_policy"]["capital"], "capital TFM"),
                   "last_equity": None, "return_pct": None, "day_return_pct": None,
                   "currency": tfm_config.get("currency", "EUR"), "equity_history": [],
                   "note": "Modelo del TFM reimplementado; regla de cartera común provisional, distinta de la tesis.",
                   "kind": item["kind"], "source": item["source"]}
            if tfm_state is not None:
                book = tfm_state["models"][TFM_IDS[item["id"]]]
                nav = _equity(book.get("nav"), item["id"])
                if not book.get("equity") or book["equity"][-1].get("date") != tfm_state.get("last_session"):
                    raise ValueError("Patrimonio TFM sin fecha válida")
                capital_tfm = row["initial_capital"]
                row.update(status="demo_con_diario", first_session=tfm_state.get("first_session"),
                           last_session=tfm_state.get("last_session"), last_equity=nav,
                           return_pct=round(100 * (nav / capital_tfm - 1), 6),
                           day_return_pct=_daily_return(book["equity"], item["id"]),
                           equity_history=_equity_history(book["equity"], item["id"]))
                row.update(_activity(None, book.get("pending"),
                                     pending_label="compras para próxima apertura"))
            rows.append(row)
        else:
            rows.append({"id": item["id"], "label": item["label"],
                         "provenance": provenance[item["id"]], "group": "historica_pendiente",
                         "status": "sin_ejecucion_comparable", "first_session": None, "last_session": None,
                         "initial_capital": None, "last_equity": None, "return_pct": None,
                         "day_return_pct": None, "currency": None, "equity_history": [],
                         "note": item["blocker"], "kind": item["kind"], "source": item["source"]})
    for row in rows:
        if "activity_state" not in row:
            if row.get("status") == "programada_sin_diario":
                row.update({
                    "activity_state": "waiting",
                    "activity_label": "Esperando primera sesión",
                    "activity_tickers": [],
                    "open_positions_count": 0,
                    "pending_orders_count": 0,
                })
            elif row.get("group") in {"historica_pendiente", "diario_heredado"}:
                row.update({
                    "activity_state": "unknown",
                    "activity_label": "Actividad actual no enlazada",
                    "activity_tickers": [],
                    "open_positions_count": 0,
                    "pending_orders_count": 0,
                })
            else:
                row.update(_activity())
        row.update(_risk_metrics(row.get("equity_history", [])))

    return {"schema_version": 1, "generated_at_utc": timestamp.isoformat(),
            "principle": "Comparar rentabilidad acumulada y riesgo observado; no ordenar carteras con distintas fechas de inicio o supuestos de ejecución.",
            "counts": {"paper_with_diary": sum(x["group"] == "paper_nuevo" and x["status"] == "demo_con_diario" for x in rows),
                       "legacy_with_diary": sum(x["status"] == "diario_heredado_observado" for x in rows),
                       "tfm_with_diary": sum(x["group"] == "tfm_demo_adaptado" and x["status"] == "demo_con_diario" for x in rows),
                       "weekly_ml_with_diary": sum(x["group"] == "weekly_ml_demo" and x["status"] == "demo_con_diario" for x in rows),
                       "tfg_with_diary": sum(x["group"] == "tfg_demo_adaptado" and x["status"] == "demo_con_diario" for x in rows),
                       "capital_cycle_with_diary": sum(x["group"] == "capital_cycle_demo" and x["status"] == "demo_con_diario" for x in rows),
                       "buy_the_dip_with_diary": sum(x["group"] == "buy_the_dip_demo" and x["status"] == "demo_con_diario" for x in rows),
                       "historical_pending": sum(x["group"] == "historica_pendiente" for x in rows)}, "tracks": rows}


def markdown(report):
    lines = ["# MIDAS: todas las ideas en paralelo", "",
             "Actualizado: " + report["generated_at_utc"] + ". El tablero distingue resultados observados de ideas aún no ejecutadas.", "",
             "La comparación principal sigue **rentabilidad acumulada + riesgo realizado**. Las campañas diarias, TFM, Weekly ML, TFG corregido, Capital Cycle, Buy The Dip y el diario genético antiguo **no forman una clasificación común** si sus fechas, divisas o reglas difieren.", "",
             "| Estrategia | Procedencia | Estado | Actividad actual | Primera fecha | Última fecha | Último periodo | Acumulada | Vol. anual. | Máx. DD | Sharpe 0rf |", "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in report["tracks"]:
        value = "—" if row["return_pct"] is None else f"{row['return_pct']:.2f} %"
        daily = "—" if row["day_return_pct"] is None else f"{row['day_return_pct']:.2f} %"
        vol = "—" if row["annualized_volatility_pct"] is None else f"{row['annualized_volatility_pct']:.2f} %"
        drawdown = "—" if row["max_drawdown_pct"] is None else f"{row['max_drawdown_pct']:.2f} %"
        sharpe = "—" if row["sharpe_0rf"] is None else f"{row['sharpe_0rf']:.2f}"
        lines.append(f"| {row['label']} | {row['provenance']} | {row['status']} | {row.get('activity_label') or '—'} | {row['first_session'] or '—'} | {row['last_session'] or '—'} | {daily} | {value} | {vol} | {drawdown} | {sharpe} |")
    lines += ["", "## Qué impide activar las líneas restantes", ""]
    for row in report["tracks"]:
        if row["group"] == "historica_pendiente":
            lines.append(f"- **{row['label']}**: {row['note']}")
    lines += ["", "La [hoja de ruta](../research/ROADMAP.md) documenta el estado de las adaptaciones. Ninguna fila pendiente recibe rentabilidad simulada retrospectivamente.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tablero de todas las estrategias MIDAS")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--paper-config", required=True)
    parser.add_argument("--paper-state", required=True)
    parser.add_argument("--legacy-state")
    parser.add_argument("--tfm-config")
    parser.add_argument("--tfm-state")
    parser.add_argument("--weekly-ml-config")
    parser.add_argument("--weekly-ml-state")
    parser.add_argument("--tfg-config")
    parser.add_argument("--tfg-state")
    parser.add_argument("--capital-cycle-config", default="capital_cycle/config.json")
    parser.add_argument("--capital-cycle-state", default="capital_cycle_state/ledger.json")
    parser.add_argument("--buy-the-dip-config", default="buy_the_dip_strategy/config.json")
    parser.add_argument("--buy-the-dip-state", default="buy_the_dip_state/ledger.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = build(_read(args.registry), _read(args.paper_config),
                   _read(args.paper_state, optional=True), _read(args.legacy_state, optional=True) if args.legacy_state else None,
                   tfm_config=_read(args.tfm_config) if args.tfm_config else None,
                   tfm_state=_read(args.tfm_state, optional=True) if args.tfm_state else None,
                   weekly_config=_read(args.weekly_ml_config) if args.weekly_ml_config else None,
                   weekly_state=_read(args.weekly_ml_state, optional=True) if args.weekly_ml_state else None,
                   tfg_config=_read(args.tfg_config) if args.tfg_config else None,
                   tfg_state=_read(args.tfg_state, optional=True) if args.tfg_state else None,
                   capital_config=_read(args.capital_cycle_config) if args.capital_cycle_config and Path(args.capital_cycle_config).exists() else None,
                   capital_state=_read(args.capital_cycle_state, optional=True) if args.capital_cycle_state else None,
                   btd_config=_read(args.buy_the_dip_config) if args.buy_the_dip_config and Path(args.buy_the_dip_config).exists() else None,
                   btd_state=_read(args.buy_the_dip_state, optional=True) if args.buy_the_dip_state else None)
    output = Path(args.output)
    _write(output / "dashboard.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    _write(output / "dashboard.md", markdown(report))
    print(json.dumps({"output": str(output), "counts": report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
