"""Transparent capital-cycle scoring for the MIDAS paper strategy."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _mean(values):
    values = [float(x) for x in values if _finite(x)]
    return statistics.fmean(values) if values else None


def _median(values):
    values = [float(x) for x in values if _finite(x)]
    return statistics.median(values) if values else None


def _ratio(a, b):
    if not _finite(a) or not _finite(b) or abs(float(b)) < 1e-12:
        return None
    return float(a) / float(b)


def _cagr(latest, oldest, periods):
    if not _finite(latest) or not _finite(oldest) or latest <= 0 or oldest <= 0 or periods <= 0:
        return None
    return (float(latest) / float(oldest)) ** (1.0 / periods) - 1.0


def _pct_rank(values, value, *, higher_better=True):
    clean = sorted(float(x) for x in values if _finite(x))
    if not clean or not _finite(value):
        return None
    x = float(value)
    if len(clean) == 1:
        rank = 50.0
    else:
        below = sum(v < x for v in clean)
        equal = sum(v == x for v in clean)
        rank = 100.0 * (below + 0.5 * equal) / len(clean)
    return rank if higher_better else 100.0 - rank


def _weighted_average(parts):
    numerator = denominator = 0.0
    for value, weight in parts:
        if _finite(value) and _finite(weight) and weight > 0:
            numerator += float(value) * float(weight)
            denominator += float(weight)
    return numerator / denominator if denominator else None


def price_features(close, benchmark_close):
    close = [float(x) for x in close if _finite(x) and x > 0]
    benchmark_close = [float(x) for x in benchmark_close if _finite(x) and x > 0]
    if len(close) < 253 or len(benchmark_close) < 253:
        return None

    def trailing_return(values, days):
        if len(values) <= days:
            return None
        return values[-1] / values[-days - 1] - 1.0

    horizon = min(756, len(close) - 1, len(benchmark_close) - 1)
    relative_36m = None
    if horizon >= 500:
        relative_36m = (close[-1] / close[-horizon - 1] - 1.0) - (
            benchmark_close[-1] / benchmark_close[-horizon - 1] - 1.0
        )
    long_window = close[-min(1260, len(close)):]
    drawdown = close[-1] / max(long_window) - 1.0
    mom_12_1 = close[-22] / close[-253] - 1.0 if len(close) >= 253 else None
    mom_6m = trailing_return(close, 126)
    sma200 = _mean(close[-200:])
    ma200_ratio = _ratio(close[-1], sma200)
    ma200_ratio = None if ma200_ratio is None else ma200_ratio - 1.0
    votes = sum(bool(x) for x in (
        _finite(mom_12_1) and mom_12_1 > 0,
        _finite(mom_6m) and mom_6m > 0,
        _finite(ma200_ratio) and ma200_ratio > 0,
    ))
    return {
        "relative_36m": relative_36m,
        "drawdown_long": drawdown,
        "momentum_12_1": mom_12_1,
        "momentum_6m": mom_6m,
        "ma200_ratio": ma200_ratio,
        "inflection_votes": votes,
        "inflection_score": 100.0 * votes / 3.0,
    }


def fundamental_features(fundamental):
    periods = list(fundamental.get("periods") or [])
    market_cap = fundamental.get("market_cap")
    if len(periods) < 3 or not _finite(market_cap) or market_cap <= 0:
        return None
    periods = sorted(periods, key=lambda row: row.get("date", ""), reverse=True)
    required = ("assets", "revenue", "ocf", "capex")
    usable = [row for row in periods if all(_finite(row.get(key)) for key in required)]
    if len(usable) < 3:
        return None
    rows = usable[:4]
    latest = rows[0]

    asset_growth_1y = _ratio(rows[0]["assets"], rows[1]["assets"])
    asset_growth_1y = None if asset_growth_1y is None else asset_growth_1y - 1.0
    asset_growth_long = _cagr(rows[0]["assets"], rows[-1]["assets"], len(rows) - 1)

    capex_ratios = []
    fcf_margins = []
    fcfs = []
    for row in rows:
        revenue = row["revenue"]
        capex = abs(float(row["capex"]))
        ocf = float(row["ocf"])
        if revenue > 0:
            capex_ratios.append(capex / revenue)
            fcf_margins.append((ocf - capex) / revenue)
        fcfs.append(ocf - capex)
    capex_intensity = _median(capex_ratios)
    latest_capex_ratio = capex_ratios[0] if capex_ratios else None
    prior_capex = _median(capex_ratios[1:]) if len(capex_ratios) > 1 else None
    capex_contraction = _ratio(latest_capex_ratio, prior_capex)
    capex_contraction = None if capex_contraction is None else capex_contraction - 1.0

    fcf_margin = _median(fcf_margins[:3])
    positive_fcf_years = sum(1 for value in fcfs[:3] if value > 0)
    normalized_fcf = _median(fcfs[:3])
    normalized_fcf_yield = _ratio(normalized_fcf, market_cap)

    operating_income = latest.get("operating_income")
    op_margin = _ratio(operating_income, latest["revenue"])
    debt = latest.get("debt")
    cash = latest.get("cash")
    if _finite(debt):
        net_debt = max(float(debt) - (float(cash) if _finite(cash) else 0.0), 0.0)
        net_debt_to_ocf = _ratio(net_debt, latest["ocf"]) if latest["ocf"] > 0 else math.inf
    else:
        net_debt_to_ocf = None

    interest = latest.get("interest_expense")
    if _finite(interest) and abs(float(interest)) > 1e-9 and _finite(operating_income):
        interest_coverage = float(operating_income) / abs(float(interest))
    elif _finite(debt) and float(debt) <= 0:
        interest_coverage = 100.0
    else:
        interest_coverage = None

    equity = latest.get("equity")
    book_to_market = _ratio(equity, market_cap) if _finite(equity) and equity > 0 else None

    return {
        "latest_statement_period": latest.get("date"),
        "asset_growth_1y": asset_growth_1y,
        "asset_growth_long": asset_growth_long,
        "capex_intensity": capex_intensity,
        "capex_contraction": capex_contraction,
        "fcf_margin": fcf_margin,
        "positive_fcf_years": positive_fcf_years,
        "normalized_fcf_yield": normalized_fcf_yield,
        "operating_margin": op_margin,
        "net_debt_to_ocf": net_debt_to_ocf,
        "interest_coverage": interest_coverage,
        "book_to_market": book_to_market,
        "ocf_latest": latest["ocf"],
    }


def score_universe(raw_candidates, config):
    """Score candidates cross-sectionally without fitting a model."""
    model = config["cycle_model"]
    rows = []
    for raw in raw_candidates:
        pf = price_features(raw["close"], raw["benchmark_close"])
        ff = fundamental_features(raw["fundamental"])
        if pf is None or ff is None:
            continue
        rows.append({
            "ticker": raw["ticker"],
            "sector": raw["sector"],
            **pf,
            **ff,
        })

    if not rows:
        return []

    by_sector = defaultdict(list)
    for row in rows:
        by_sector[row["sector"]].append(row)

    sector_raw = {}
    for sector, peers in by_sector.items():
        sector_raw[sector] = {
            "asset_growth_1y": _median([x["asset_growth_1y"] for x in peers]),
            "capex_contraction": _median([x["capex_contraction"] for x in peers]),
            "relative_36m": _median([x["relative_36m"] for x in peers]),
            "drawdown_long": _median([x["drawdown_long"] for x in peers]),
        }
    sectors = list(sector_raw)
    sector_scores = {}
    for sector in sectors:
        vals = sector_raw[sector]
        parts = []
        for key in ("asset_growth_1y", "capex_contraction", "relative_36m", "drawdown_long"):
            parts.append((_pct_rank([sector_raw[s][key] for s in sectors], vals[key], higher_better=False), 1.0))
        sector_scores[sector] = _weighted_average(parts) or 50.0

    for sector, peers in by_sector.items():
        metrics = {
            key: [row[key] for row in peers]
            for key in (
                "asset_growth_1y", "asset_growth_long", "capex_contraction",
                "relative_36m", "drawdown_long", "fcf_margin", "positive_fcf_years",
                "operating_margin", "net_debt_to_ocf", "interest_coverage",
                "book_to_market", "normalized_fcf_yield",
            )
        }
        for row in peers:
            firm_scarcity = _weighted_average([
                (_pct_rank(metrics["asset_growth_1y"], row["asset_growth_1y"], higher_better=False), 0.22),
                (_pct_rank(metrics["asset_growth_long"], row["asset_growth_long"], higher_better=False), 0.18),
                (_pct_rank(metrics["capex_contraction"], row["capex_contraction"], higher_better=False), 0.22),
                (_pct_rank(metrics["relative_36m"], row["relative_36m"], higher_better=False), 0.20),
                (_pct_rank(metrics["drawdown_long"], row["drawdown_long"], higher_better=False), 0.18),
            ])
            row["sector_scarcity_score"] = sector_scores[sector]
            row["capital_scarcity_score"] = _weighted_average([
                (firm_scarcity, 0.65), (sector_scores[sector], 0.35)
            ])

            row["quality_score"] = _weighted_average([
                (_pct_rank(metrics["fcf_margin"], row["fcf_margin"], higher_better=True), 0.25),
                (_pct_rank(metrics["positive_fcf_years"], row["positive_fcf_years"], higher_better=True), 0.15),
                (_pct_rank(metrics["operating_margin"], row["operating_margin"], higher_better=True), 0.20),
                (_pct_rank(metrics["net_debt_to_ocf"], row["net_debt_to_ocf"], higher_better=False), 0.20),
                (_pct_rank(metrics["interest_coverage"], row["interest_coverage"], higher_better=True), 0.20),
            ])
            row["valuation_score"] = _weighted_average([
                (_pct_rank(metrics["book_to_market"], row["book_to_market"], higher_better=True), 0.45),
                (_pct_rank(metrics["normalized_fcf_yield"], row["normalized_fcf_yield"], higher_better=True), 0.55),
            ])
            weights = model["weights"]
            row["composite_score"] = _weighted_average([
                (row["capital_scarcity_score"], weights["capital_scarcity"]),
                (row["quality_score"], weights["survivor_quality"]),
                (row["valuation_score"], weights["valuation"]),
                (row["inflection_score"], weights["inflection"]),
            ])

            capex_ok = _finite(row["capex_intensity"]) and row["capex_intensity"] >= model["minimum_capex_to_revenue"]
            cash_ok = _finite(row["ocf_latest"]) and row["ocf_latest"] > 0
            fcf_ok = row["positive_fcf_years"] >= model["minimum_positive_fcf_years"]
            debt_ok = (not _finite(row["net_debt_to_ocf"]) or
                       row["net_debt_to_ocf"] <= model["maximum_net_debt_to_ocf"])
            coverage_ok = (not _finite(row["interest_coverage"]) or
                           row["interest_coverage"] >= model["minimum_interest_coverage"])
            row["survival_gate"] = bool(cash_ok and fcf_ok and debt_ok and coverage_ok)
            row["entry_eligible"] = bool(
                capex_ok and row["survival_gate"] and
                _finite(row["quality_score"]) and row["quality_score"] >= model["minimum_quality_score"] and
                row["sector_scarcity_score"] >= model["minimum_sector_scarcity_score"] and
                row["inflection_votes"] >= model["inflection_min_votes"] and
                _finite(row["composite_score"]) and row["composite_score"] >= model["entry_score"]
            )
            row["hard_exit"] = bool(
                not row["survival_gate"] or
                row["inflection_votes"] <= model["hard_exit_inflection_votes"] or
                (_finite(row["composite_score"]) and row["composite_score"] < model["hard_exit_score"])
            )

    return sorted(rows, key=lambda x: (-(x["composite_score"] if _finite(x["composite_score"]) else -math.inf), x["ticker"]))


def months_between(start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return (b.year - a.year) * 12 + b.month - a.month


def choose_portfolio(scored, positions, asof, config):
    """Apply hysteresis: hard exits immediately; otherwise keep valid names before adding new ones."""
    model, policy = config["cycle_model"], config["paper_policy"]
    lookup = {row["ticker"]: row for row in scored}
    kept = []
    exit_reasons = {}

    for ticker, position in sorted((positions or {}).items()):
        row = lookup.get(ticker)
        if row is None:
            exit_reasons[ticker] = "data_missing"
            continue
        held = months_between(position["entry_date"], asof)
        if row["hard_exit"]:
            exit_reasons[ticker] = "hard_cycle_or_quality_exit"
            continue
        if held >= model["minimum_hold_months"] and row["composite_score"] < model["retention_score"]:
            exit_reasons[ticker] = "score_below_retention"
            continue
        kept.append(ticker)

    max_positions = int(policy["max_positions"])
    max_sector = int(policy["max_sector_positions"])
    selected = []
    sector_counts = defaultdict(int)
    for ticker in kept:
        if len(selected) >= max_positions:
            break
        row = lookup[ticker]
        if sector_counts[row["sector"]] >= max_sector:
            exit_reasons[ticker] = "sector_cap"
            continue
        selected.append(ticker)
        sector_counts[row["sector"]] += 1

    for row in scored:
        if len(selected) >= max_positions:
            break
        ticker = row["ticker"]
        if ticker in selected or not row["entry_eligible"]:
            continue
        if sector_counts[row["sector"]] >= max_sector:
            continue
        selected.append(ticker)
        sector_counts[row["sector"]] += 1

    if not selected:
        return {}, exit_reasons
    weight = min(
        float(policy["max_position_weight"]),
        float(policy["invest_fraction"]) / len(selected),
    )
    return {ticker: weight for ticker in selected}, exit_reasons
