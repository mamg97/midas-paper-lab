"""Run the corrected TFG paper campaign after the last US session of each week."""

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from data import build_signal, is_week_end_session, live_panel
from paper import advance, digest


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


def _write_markdown(path, signal, state):
    lines = [
        "# TFG Corrected 2026 — estado paper",
        "",
        f"**Última señal:** {signal['asof']}",
        f"**Estado de señal:** {signal['status']}",
        f"**NAV:** {state['nav']:,.2f} {state['currency']}",
        f"**Rentabilidad acumulada:** {100 * (state['nav'] / state['equity'][0]['nav'] - 1):+.3f} %",
        "",
        "## Embudo TFG",
        "",
        f"- universo evaluado: **{signal.get('universe_count', 0)}**",
        f"- filtro técnico: **{signal.get('technical_candidates', 0)}** candidatos",
        f"- filtro multicriterio: **{signal.get('stage2_candidates', 0)}** candidatos",
        f"- cartera final: **{len(signal.get('selections', []))}** posiciones",
        "",
    ]
    if signal.get("selections"):
        lines += [
            "## Selección actual",
            "",
            "| # | Ticker | Peso | AHP corregido | Retorno diario 40d | MAD 40d | Beta SPY |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for index, item in enumerate(signal["selections"], 1):
            lines.append(
                f"| {index} | **{item['ticker']}** | {100*item['weight']:.2f}% | "
                f"{item['ahp_corrected_score']:.4f} | {100*item['mean_daily_return']:.3f}% | "
                f"{100*item['mad_40']:.3f}% | {item['beta_spy']:.3f} |"
            )
        lines.append("")

    if state.get("trades"):
        last = state["trades"][-1]
        lines += [
            "## Última semana liquidada",
            "",
            f"- señal: **{last['signal_date']}**",
            f"- entrada: **{last['entry_date'] or '—'}**",
            f"- salida: **{last['exit_date'] or '—'}**",
            f"- motivo: **{last['exit_reason']}**",
            f"- retorno neto: **{last['return_pct']:+.3f} %**",
            "",
        ]

    lines += [
        "## Contrato",
        "",
        "Esta es la variante **TFG corregido 2026**. No es el resultado histórico del TFG de 2021. "
        "Señal al cierre semanal, ejecución paper en la apertura siguiente, costes explícitos, "
        "acciones fraccionadas y stop causal.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def run(config_path, output_dir, now=None):
    config = _read(config_path)
    if config.get("schema_version") != 1 or config.get("calendar") != "XNYS":
        raise ValueError("Configuración TFG no admitida")

    config_path = Path(config_path)
    root = config_path.parent.parent
    universe_path = root / config["universe_file"]

    snapshot = live_panel(config, universe_path, now=now)
    if snapshot is None:
        return {"status": "market_closed", "changed": False}
    panel, meta, usable, failures, asof = snapshot

    if not is_week_end_session(asof):
        return {"status": "not_week_end", "session": asof, "changed": False}

    output = Path(output_dir)
    signal_path = output / "signals" / f"{asof}.json"
    state_path = output / "ledger.json"

    if signal_path.exists():
        signal = _read(signal_path)
        if signal.get("asof") != asof:
            raise ValueError("Archivo de señal TFG inconsistente")
    else:
        signal = build_signal(config, panel, meta, usable, asof)
        signal["schema_version"] = 1
        signal["kind"] = "TFG_CORRECTED_2026"
        signal["version"] = config["version"]
        signal["config_hash"] = digest(config)
        signal["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
        signal["market_failures"] = failures
        _write(signal_path, signal)

    state = _read(state_path) if state_path.exists() else None
    state, changed = advance(config, panel, signal, state)
    if changed or not state_path.exists():
        _write(state_path, state)
    _write_markdown(output / "latest.md", signal, state)

    return {
        "status": "signal_recorded" if changed else "already_recorded",
        "session": asof,
        "signal_status": signal["status"],
        "technical_candidates": signal.get("technical_candidates", 0),
        "stage2_candidates": signal.get("stage2_candidates", 0),
        "positions": len(signal.get("selections", [])),
        "nav": state["nav"],
        "changed": changed,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="TFG corrected 2026 paper campaign")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args.config, args.output), ensure_ascii=False))
        return 0
    except Exception as exc:
        print("Error TFG corrected: " + repr(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
