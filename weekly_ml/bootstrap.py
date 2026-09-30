"""One-off non-prospective smoke bootstrap for MIDAS Weekly ML.

This intentionally replays a historical cutoff to verify that the full pipeline can train,
select, size and simulate fills. Its results MUST NOT be mixed with the official forward
paper ledger.
"""

import argparse
import json
import math
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from data import _extract_download, build_dataset, load_universe
from models import fit_predict
from paper import advance, BENCHMARKS, digest, _fractional_quantity


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _markdown(path, report):
    lines = [
        "# MIDAS Weekly ML — bootstrap no prospectivo",
        "",
        f"**Señal simulada:** {report['signal_asof']}",
        f"**Entrada simulada:** {report['entry_date']}",
        f"**Valoración:** cierre de {report['mark_date']}",
        "",
        "> Este resultado sirve únicamente para comprobar que todo el pipeline funciona. "
        "Se ha calculado después de conocer esas fechas y no cuenta como rentabilidad forward.",
        "",
        "## Resumen",
        "",
        "| Estrategia | Posiciones | NAV cierre | Retorno MTM | Liquidación estimada |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, item in report["strategies"].items():
        lines.append(
            f"| {name} | {len(item['positions'])} | "
            f"USD {item['mark_to_market_nav']:,.2f} | {item['mark_to_market_return_pct']:.3f}% | "
            f"USD {item['estimated_liquidation_nav']:,.2f} |"
        )
    lines += ["", "## Selecciones", ""]
    for name, item in report["strategies"].items():
        lines.append(f"### {name}")
        if not item["positions"]:
            lines += ["", "Sin posiciones.", ""]
            continue
        lines += ["", "| Ticker | Acciones | Apertura | Compra simulada | Cierre | P&L MTM |",
                  "| --- | ---: | ---: | ---: | ---: | ---: |"]
        for row in item["positions"]:
            lines.append(
                f"| {row['ticker']} | {row['quantity']} | {row['raw_open']:.2f} | "
                f"{row['buy_price']:.2f} | {row['mark_close']:.2f} | {row['mtm_pnl']:.2f} |"
            )
        lines.append("")
    ensemble = report.get("ensemble_top20", [])
    if ensemble:
        lines += ["## Top 20 del ensemble", "",
                  "| # | Ticker | Score | Retorno predicho | Votos positivos | Dispersión |",
                  "| ---: | --- | ---: | ---: | ---: | ---: |"]
        for i, row in enumerate(ensemble, start=1):
            lines.append(
                f"| {i} | {row['ticker']} | {row['score']:.4f} | "
                f"{100*row['predicted_return']:.3f}% | {row['positive_votes']} | "
                f"{row['rank_dispersion']:.4f} |"
            )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _bootstrap_panel(config, universe_path, signal_asof, mark_asof):
    """Download only the history needed for the explicitly retrospective smoke replay.

    This bypasses the production eligible-session guard on purpose, but stays isolated in
    bootstrap.py so the official forward runner cannot create retrospective signals.
    """
    signal_date = date.fromisoformat(signal_asof)
    mark_date = date.fromisoformat(mark_asof)
    if mark_date <= signal_date:
        raise ValueError("mark_asof debe ser posterior a signal_asof")

    symbols, sectors = load_universe(universe_path)
    requested = symbols + [x for x in config["benchmark_tickers"] if x not in symbols]

    import yfinance as yf

    panel = {}
    failures = {}
    start_date = signal_date - timedelta(days=365 * 7)
    end_date = mark_date + timedelta(days=1)
    for start in range(0, len(requested), 60):
        chunk = requested[start:start + 60]
        data = yf.download(
            chunk,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
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
            frame = frame.loc[frame.index.date <= mark_date]
            if frame.empty:
                failures[ticker] = "empty_before_mark"
                continue
            panel[ticker] = frame

    usable = []
    minimum = int(config["feature_min_history_days"])
    for ticker in symbols:
        frame = panel.get(ticker)
        if frame is None:
            continue
        history = frame.loc[frame.index.date <= signal_date]
        if history.empty or history.index[-1].date() != signal_date:
            failures[ticker] = "missing_signal_cutoff"
            continue
        if len(history) < minimum:
            failures[ticker] = f"history_{len(history)}"
            continue
        usable.append(ticker)

    for benchmark in config["benchmark_tickers"]:
        frame = panel.get(benchmark)
        if frame is None:
            raise ValueError("Benchmark sin datos: " + benchmark)
        if signal_date not in set(frame.index.date):
            raise ValueError("Benchmark sin cierre de señal: " + benchmark)
        if mark_date not in set(frame.index.date):
            raise ValueError("Benchmark sin cierre de valoración: " + benchmark)

    if len(usable) < 350:
        raise ValueError(f"Universo bootstrap utilizable demasiado pequeño: {len(usable)}")
    return panel, sectors, usable, failures


def _portfolio_snapshot(name, book, panel, policy, signal_asof, mark_asof):
    capital = float(policy["capital"])
    orders = book.get("pending", [])
    budget_each = 0.0
    if orders:
        if name in BENCHMARKS:
            budget_each = capital * float(policy["invest_fraction"])
        else:
            budget_each = min(
                capital * float(policy["max_entry_weight"]),
                capital * float(policy["invest_fraction"]) / len(orders),
            )
    cash = capital
    positions = []
    for order in orders:
        ticker = order["ticker"]
        frame = panel[ticker]
        after_signal = frame.loc[frame.index.date > datetime.fromisoformat(signal_asof).date()]
        if after_signal.empty:
            continue
        entry_row = after_signal.iloc[0]
        entry_date = after_signal.index[0].date().isoformat()
        marked = frame.loc[frame.index.date == datetime.fromisoformat(mark_asof).date()]
        if marked.empty:
            continue
        mark_close = float(marked.iloc[-1]["close"])
        raw_open = float(entry_row["open"])
        buy_price = raw_open * (1 + float(policy["slippage"]))
        qty = _fractional_quantity(budget_each, buy_price, policy)
        if qty <= 0:
            continue
        buy_fee = qty * buy_price * float(policy["commission"])
        cash_out = qty * buy_price + buy_fee
        cash -= cash_out
        mark_value = qty * mark_close
        hypothetical_sell = mark_close * (1 - float(policy["slippage"]))
        hypothetical_fee = qty * hypothetical_sell * float(policy["commission"])
        hypothetical_liquidation = qty * hypothetical_sell - hypothetical_fee
        positions.append({
            **order,
            "entry_date": entry_date,
            "raw_open": raw_open,
            "buy_price": buy_price,
            "quantity": qty,
            "buy_commission": buy_fee,
            "mark_date": mark_asof,
            "mark_close": mark_close,
            "mark_value": mark_value,
            "mtm_pnl": mark_value - cash_out,
            "estimated_liquidation_value": hypothetical_liquidation,
        })
    mtm_nav = cash + sum(x["mark_value"] for x in positions)
    liquidation_nav = cash + sum(x["estimated_liquidation_value"] for x in positions)
    return {
        "positions": positions,
        "cash_after_entries": cash,
        "mark_to_market_nav": mtm_nav,
        "mark_to_market_return_pct": 100 * (mtm_nav / capital - 1),
        "estimated_liquidation_nav": liquidation_nav,
        "estimated_liquidation_return_pct": 100 * (liquidation_nav / capital - 1),
    }


def run(config_path, output_dir, signal_asof, mark_asof):
    config = _read(config_path)
    config_path = Path(config_path)
    root = config_path.parent.parent
    universe_path = root / config["universe_file"]

    panel, sectors, usable, market_failures = _bootstrap_panel(
        config, universe_path, signal_asof, mark_asof
    )

    labelled, live, feature_exclusions = build_dataset(panel, sectors, usable, signal_asof)
    predictions, validation, training = fit_predict(config, labelled, live)

    forecast = {
        "schema_version": 1,
        "asof": signal_asof,
        "horizon": "next_week_first_open_to_last_close",
        "currency": config["currency"],
        "source_family": "NON_PROSPECTIVE_BOOTSTRAP",
        "version": config["version"],
        "config_hash": digest(config),
        "models": predictions,
    }
    initialized, _ = advance(config, panel, forecast, None)
    strategies = {
        name: _portfolio_snapshot(name, book, panel, config["paper_policy"], signal_asof, mark_asof)
        for name, book in initialized["strategies"].items()
    }
    ensemble = predictions["ensemble_consensus"]
    top20 = sorted(
        [{"ticker": ticker, **values} for ticker, values in ensemble.items()],
        key=lambda x: (-x["score"], x["ticker"]),
    )[:20]

    entry_dates = sorted({
        row["entry_date"] for item in strategies.values() for row in item["positions"]
    })
    report = {
        "schema_version": 1,
        "kind": "NON_PROSPECTIVE_BOOTSTRAP",
        "excluded_from_forward_performance": True,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "signal_asof": signal_asof,
        "entry_date": entry_dates[0] if len(entry_dates) == 1 else entry_dates,
        "mark_date": mark_asof,
        "bootstrap_data_cutoff": mark_asof,
        "training": training,
        "validation": validation,
        "universe": {
            "configured": len(sectors),
            "download_usable": len(usable),
            "live_features_at_signal": len(live),
            "market_failures": len(market_failures),
            "feature_exclusions": len(feature_exclusions),
        },
        "strategies": strategies,
        "ensemble_top20": top20,
    }
    out = Path(output_dir)
    _write(out / f"bootstrap_{signal_asof}.json", report)
    _markdown(out / f"bootstrap_{signal_asof}.md", report)
    return {
        "status": "bootstrap_recorded",
        "signal_asof": signal_asof,
        "mark_asof": mark_asof,
        "tracks": len(strategies),
        "ensemble_positions": len(strategies["ensemble_consensus"]["positions"]),
        "excluded_from_forward_performance": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--output", required=True)
    parser.add_argument("--signal-asof", required=True)
    parser.add_argument("--mark-asof", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.config, args.output, args.signal_asof, args.mark_asof),
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
