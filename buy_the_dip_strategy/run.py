"""Run the Buy The Dip corpus v0 demo after a fully closed XNYS session."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from engine import STRATEGY_ID, advance, benchmark_return_pct
from factors import choose_portfolio, score_universe
from market import (
    calendar_context,
    close_series,
    current_bar,
    download_panel,
    eligible_session,
    fundamentals_snapshot,
    load_universe,
)


def _read(path, optional=False):
    path = Path(path)
    if optional and not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _month_index(day):
    year, month, _ = map(int, day.split("-"))
    return year * 12 + month


def _decision_due(state, asof, is_month_end):
    if not state or not state.get("last_signal_session"):
        return True
    if is_month_end:
        return state.get("last_signal_session") != asof
    return _month_index(asof) - _month_index(state["last_signal_session"]) >= 2


def _build_decision(config, state, asof, context, panel, sectors, fundamentals,
                    price_failures, fundamental_failures):
    benchmark = config["benchmark_ticker"]
    benchmark_close = close_series(panel[benchmark])
    raw = []
    for ticker, fundamental in fundamentals.items():
        frame = panel.get(ticker)
        if frame is None:
            continue
        raw.append({
            "ticker": ticker,
            "sector": sectors[ticker],
            "close": close_series(frame),
            "benchmark_close": benchmark_close,
            "fundamental": fundamental,
        })

    scored = score_universe(raw, config)
    if len(scored) < int(config["minimum_valid_candidates"]):
        raise ValueError(f"Cobertura fundamental insuficiente: {len(scored)} candidatos puntuables")

    positions = {} if state is None else state.get("positions", {})
    target_weights, exit_reasons, invest_fraction = choose_portfolio(
        scored, positions, asof, config
    )
    lookup = {row["ticker"]: row for row in scored}
    selected = []
    for ticker, weight in target_weights.items():
        row = lookup[ticker]
        selected.append({
            "ticker": ticker,
            "sector": row["sector"],
            "weight": round(weight, 8),
            "composite_score": round(row["composite_score"], 4),
            "valuation_score": round(row["valuation_score"], 4) if row["valuation_score"] is not None else None,
            "quality_score": round(row["quality_score"], 4) if row["quality_score"] is not None else None,
            "capital_allocation_score": round(row["capital_allocation_score"], 4) if row["capital_allocation_score"] is not None else None,
            "dislocation_score": round(row["dislocation_score"], 4) if row["dislocation_score"] is not None else None,
            "catalyst_votes": int(row["catalyst_votes"]),
            "volatility_1y": round(row["volatility_1y"], 6) if row["volatility_1y"] is not None else None,
            "latest_statement_period": row["latest_statement_period"],
        })
    selected.sort(key=lambda x: (-x["composite_score"], x["ticker"]))

    return {
        "signal_date": asof,
        "expected_fill_session": context["next_session"],
        "target_weights": target_weights,
        "sectors": {ticker: sectors[ticker] for ticker in target_weights},
        "selected": selected,
        "invest_fraction": invest_fraction,
        "exit_reasons": exit_reasons,
        "excluded_count": len(set(sectors) - set(fundamentals)),
        "coverage": {
            "frozen_universe": len(sectors),
            "price_usable": len([ticker for ticker in sectors if ticker in panel]),
            "fundamental_usable": len(fundamentals),
            "scored": len(scored),
            "entry_eligible": sum(bool(row["entry_eligible"]) for row in scored),
            "financials_scored": sum(bool(row["financial_sector"]) for row in scored),
            "price_failures": len(price_failures),
            "fundamental_failures": len(fundamental_failures),
        },
    }


def run(config_path, output_dir, now=None):
    config_path = Path(config_path)
    config = _read(config_path)
    if config.get("schema_version") != 1 or config.get("name") != "MIDAS_buy_the_dip_corpus_v0_2026":
        raise ValueError("Configuración Buy The Dip no reconocida")
    if config.get("currency") != "USD":
        raise ValueError("La campaña Buy The Dip requiere USD")

    asof = eligible_session(config.get("calendar", "XNYS"), now=now)
    if asof is None:
        return {"status": "market_closed", "changed": False}
    context = calendar_context(asof, config.get("calendar", "XNYS"))
    output = Path(output_dir)
    state_path = output / "ledger.json"
    state = _read(state_path, optional=True)

    universe_path = Path(config["universe_file"])
    universe_hash = _file_hash(universe_path)
    if state is not None and state.get("universe_hash") not in (None, universe_hash):
        raise ValueError("El universo congelado cambió: iniciar otra campaña")

    symbols, sectors, _ = load_universe(universe_path)
    benchmark = config["benchmark_ticker"]
    due = _decision_due(state, asof, context["is_month_end"])

    active = set()
    if state:
        active |= set(state.get("positions", {}))
        pending = state.get("pending")
        if pending:
            active |= set(pending.get("target_weights", {}))

    if due:
        requested = symbols + ([benchmark] if benchmark not in symbols else [])
        panel, price_failures = download_panel(
            requested, period=config["history_period"], asof=asof,
            min_history=int(config["price_min_history_days"]),
        )
        if benchmark not in panel:
            raise ValueError("Benchmark sin historial completo")
        fundamentals, fundamental_failures = fundamentals_snapshot(
            [ticker for ticker in symbols if ticker in panel], sectors,
            asof=asof, workers=int(config.get("fundamental_workers", 8)),
        )
        decision = _build_decision(
            config, state, asof, context, panel, sectors, fundamentals,
            price_failures, fundamental_failures,
        )
    else:
        requested = sorted(active | {benchmark})
        panel, price_failures = download_panel(
            requested, period="6mo", asof=asof, min_history=1,
        )
        missing = sorted(set(requested) - set(panel))
        if missing:
            raise ValueError("No se pueden valorar posiciones/órdenes: " + ",".join(missing))
        decision = None
        fundamental_failures = {}

    bars = {ticker: current_bar(frame) for ticker, frame in panel.items()}
    updated, changed = advance(
        config, bars, asof, bars[benchmark]["close"], decision=decision, state=state,
    )
    updated["universe_hash"] = universe_hash
    if changed:
        _atomic_json(state_path, updated)
        if decision is not None:
            _atomic_json(output / "signals" / f"{asof}.json", decision)

    return {
        "status": "ok",
        "strategy_id": STRATEGY_ID,
        "session": asof,
        "month_end": context["is_month_end"],
        "decision_recorded": decision is not None,
        "changed": changed,
        "nav": updated["nav"],
        "positions": len(updated["positions"]),
        "cash": updated["cash"],
        "pending_targets": 0 if not updated.get("pending") else len(updated["pending"]["target_weights"]),
        "benchmark_return_pct": benchmark_return_pct(updated),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Buy The Dip corpus v0 demo; nunca envía órdenes reales")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args.config, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Error Buy The Dip demo: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
