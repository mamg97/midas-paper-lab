"""Render a compact human-readable dashboard for MIDAS Weekly ML."""

import argparse
import json
from pathlib import Path

MODEL_META = {
    "lgbm_return": ("LightGBM Return", "Predice la rentabilidad semanal esperada de cada acción."),
    "lgbm_direction": ("LightGBM Direction", "Estima la probabilidad de que la semana termine en positivo."),
    "lgbm_ranker": ("LightGBM Ranker", "Ordena el universo de mejor a peor oportunidad relativa."),
    "mlp_return": ("MLP", "Red neuronal feed-forward sobre features tabulares."),
    "lstm_return": ("LSTM", "Red temporal sobre la secuencia de las últimas 26 semanas."),
    "arima_return": ("ARIMA", "Modelo estadístico por acción sobre retornos semanales."),
    "ensemble_consensus": ("Ensemble", "Combina rankings y votos de los expertos anteriores."),
    "benchmark_spy": ("SPY", "Benchmark S&P 500."),
    "benchmark_rsp": ("RSP", "Benchmark S&P 500 equiponderado."),
}
ORDER = list(MODEL_META)


def _read(path, optional=False):
    path = Path(path)
    if optional and not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _metric_text(metrics):
    if not metrics:
        return "—"
    out = []
    if metrics.get("accuracy") is not None:
        out.append(f"accuracy {100*metrics['accuracy']:.1f}%")
    if metrics.get("direction_accuracy") is not None:
        out.append(f"direction {100*metrics['direction_accuracy']:.1f}%")
    if metrics.get("brier") is not None:
        out.append(f"Brier {metrics['brier']:.4f}")
    if metrics.get("rank_ic") is not None:
        out.append(f"rank-IC {metrics['rank_ic']:.4f}")
    if metrics.get("mae") is not None:
        out.append(f"MAE {100*metrics['mae']:.2f} pp")
    if metrics.get("best_iteration") is not None:
        out.append(f"iter {metrics['best_iteration']}")
    return " · ".join(out) if out else "—"


def _top_predictions(model, values, n=10):
    rows = []
    for ticker, item in values.items():
        item = dict(item)
        item["ticker"] = ticker
        rows.append(item)
    if model == "lgbm_direction":
        rows.sort(key=lambda x: (-float(x["direction_probability"]), x["ticker"]))
    elif model == "lgbm_ranker":
        rows.sort(key=lambda x: (-float(x["rank_score"]), x["ticker"]))
    elif model == "ensemble_consensus":
        rows.sort(key=lambda x: (-float(x["score"]), x["ticker"]))
    else:
        rows.sort(key=lambda x: (-float(x["predicted_return"]), x["ticker"]))
    return rows[:n]


def build(forecast=None, ledger=None, bootstrap=None):
    lines = ["# MIDAS Weekly ML — dashboard", ""]

    if forecast:
        lines += [
            f"> **Forward activo.** Última señal registrada: **{forecast['asof']}**. "
            "Las predicciones mostradas abajo fueron congeladas antes de conocer la semana objetivo.",
            "",
        ]
    elif bootstrap:
        lines += [
            "> **Aún sin señal forward oficial.** Se muestra el bootstrap técnico del "
            f"**{bootstrap['signal_asof']}**, marcado como no prospectivo y excluido del track record.",
            "",
        ]
    else:
        lines += ["> Campaña preparada, todavía sin forecast ni bootstrap disponible.", ""]

    lines += ["## Progreso", "",
              "| Modelo | Función | Estado | NAV | Retorno acumulado | Posiciones/órdenes | Trades cerrados |",
              "| --- | --- | --- | ---: | ---: | ---: | ---: |"]

    for key in ORDER:
        label, desc = MODEL_META[key]
        if ledger and key in ledger.get("strategies", {}):
            book = ledger["strategies"][key]
            nav = float(book["nav"])
            first = float(book["equity"][0]["nav"]) if book.get("equity") else nav
            ret = 100 * (nav / first - 1) if first else 0.0
            lines.append(
                f"| **{label}** | {desc} | forward | {nav:,.2f} USD | {ret:.3f}% | "
                f"{len(book.get('pending', []))} | {len(book.get('trades', []))} |"
            )
        elif bootstrap and key in bootstrap.get("strategies", {}):
            item = bootstrap["strategies"][key]
            lines.append(
                f"| **{label}** | {desc} | bootstrap | {item['mark_to_market_nav']:,.2f} USD | "
                f"{item['mark_to_market_return_pct']:.3f}% | {len(item.get('positions', []))} | 0 |"
            )
        else:
            lines.append(f"| **{label}** | {desc} | preparado | — | — | — | — |")

    if forecast:
        lines += ["", "## Predicciones del último forecast", "",
                  f"**Cutoff:** {forecast['asof']} · **Horizonte:** primera apertura → último cierre de la semana siguiente.", ""]
        validation = forecast.get("validation", {})
        for key in ["lgbm_return", "lgbm_direction", "lgbm_ranker",
                    "mlp_return", "lstm_return", "arima_return", "ensemble_consensus"]:
            label, desc = MODEL_META[key]
            values = forecast["models"].get(key, {})
            lines += [f"### {label}", "", desc, "",
                      f"**Validación diagnóstica:** {_metric_text(validation.get(key, {}))}", ""]
            top = _top_predictions(key, values, 10)
            if not top:
                lines += ["Sin predicciones.", ""]
                continue
            if key == "lgbm_direction":
                lines += ["| # | Ticker | Prob. positiva |", "| ---: | --- | ---: |"]
                for i, row in enumerate(top, 1):
                    lines.append(f"| {i} | **{row['ticker']}** | {100*row['direction_probability']:.1f}% |")
            elif key == "lgbm_ranker":
                lines += ["| # | Ticker | Rank score |", "| ---: | --- | ---: |"]
                for i, row in enumerate(top, 1):
                    lines.append(f"| {i} | **{row['ticker']}** | {row['rank_score']:.4f} |")
            elif key == "ensemble_consensus":
                lines += ["| # | Ticker | Score | Retorno previsto | Votos + | Dispersión |",
                          "| ---: | --- | ---: | ---: | ---: | ---: |"]
                for i, row in enumerate(top, 1):
                    lines.append(
                        f"| {i} | **{row['ticker']}** | {row['score']:.4f} | "
                        f"{100*row['predicted_return']:.2f}% | {row['positive_votes']} | "
                        f"{row['rank_dispersion']:.4f} |"
                    )
            else:
                lines += ["| # | Ticker | Retorno previsto |", "| ---: | --- | ---: |"]
                for i, row in enumerate(top, 1):
                    lines.append(f"| {i} | **{row['ticker']}** | {100*row['predicted_return']:.2f}% |")
            lines.append("")

    elif bootstrap:
        lines += ["", "## Predicciones del bootstrap", "",
                  f"Señal reconstruida: **{bootstrap['signal_asof']}** · entrada: **{bootstrap['entry_date']}** · "
                  f"valoración: **{bootstrap['mark_date']}**. **No cuenta como forward.**", ""]
        for key in ["lgbm_return", "lgbm_direction", "lgbm_ranker",
                    "mlp_return", "lstm_return", "arima_return"]:
            label, desc = MODEL_META[key]
            item = bootstrap["strategies"][key]
            lines += [f"### {label}", "", desc, "",
                      f"**Validación diagnóstica:** {_metric_text(bootstrap.get('validation', {}).get(key, {}))}", ""]
            positions = item.get("positions", [])
            if not positions:
                lines += ["No abrió posiciones con el umbral de esta cartera individual.", ""]
                continue
            lines += ["| # | Ticker | Señal | Entrada | Cierre bootstrap | P&L MTM |",
                      "| ---: | --- | ---: | ---: | ---: | ---: |"]
            for i, row in enumerate(positions, 1):
                if row.get("direction_probability") is not None:
                    signal = f"{100*row['direction_probability']:.1f}% prob."
                elif row.get("predicted_return") is not None:
                    signal = f"{100*row['predicted_return']:.2f}%"
                else:
                    signal = f"{row['score']:.4f}"
                lines.append(
                    f"| {i} | **{row['ticker']}** | {signal} | {row['buy_price']:.2f} | "
                    f"{row['mark_close']:.2f} | {row['mtm_pnl']:.2f} USD |"
                )
            lines.append("")
        lines += ["### Ensemble", "",
                  "Top del consenso reconstruido:", "",
                  "| # | Ticker | Score | Retorno previsto | Votos + | Dispersión |",
                  "| ---: | --- | ---: | ---: | ---: | ---: |"]
        for i, row in enumerate(bootstrap.get("ensemble_top20", [])[:10], 1):
            lines.append(
                f"| {i} | **{row['ticker']}** | {row['score']:.4f} | "
                f"{100*row['predicted_return']:.2f}% | {row['positive_votes']} | "
                f"{row['rank_dispersion']:.4f} |"
            )

    lines += [
        "", "## Cómo interpretarlo", "",
        "- **Predicción ≠ rentabilidad realizada.**",
        "- La validación cronológica sirve para diagnóstico; no se suma al track record demo.",
        "- El bootstrap está excluido del forward.",
        "- Cuando exista ledger forward, el NAV y los trades cerrados de cada experto se acumularán aquí.",
        "- SPY y RSP son referencias, no modelos.",
        "",
        "## Fuentes", "",
        "- weekly_ml_state/forecasts/: forecasts forward inmutables.",
        "- weekly_ml_state/ledger.json: NAV, órdenes y trades forward.",
        "- weekly_ml_bootstrap_state/: bootstrap técnico inicial.",
        "- strategy_state/dashboard.md: comparador global de todas las estrategias MIDAS.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecast")
    parser.add_argument("--ledger")
    parser.add_argument("--bootstrap")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    forecast = _read(args.forecast, optional=True) if args.forecast else None
    ledger = _read(args.ledger, optional=True) if args.ledger else None
    bootstrap = _read(args.bootstrap, optional=True) if args.bootstrap else None
    Path(args.output).write_text(build(forecast, ledger, bootstrap) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
