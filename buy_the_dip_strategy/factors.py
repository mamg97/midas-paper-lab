"""Transparent Buy The Dip corpus v0 scoring.

The source corpus supports the process dimensions (cheap/free-cash-flow, balance
sheet resilience, capital allocation, dislocation, catalysts and patient rotation).
The exact numerical weights below are an automation design choice frozen before
the first fill; they are not presented as numbers stated by the podcast hosts.
"""

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


def _trailing_return(values, days):
    if len(values) <= days:
        return None
    return values[-1] / values[-days - 1] - 1.0


def price_features(close, benchmark_close):
    close = [float(x) for x in close if _finite(x) and x > 0]
    benchmark_close = [float(x) for x in benchmark_close if _finite(x) and x > 0]
    if len(close) < 253 or len(benchmark_close) < 253:
        return None

    horizon = min(756, len(close) - 1, len(benchmark_close) - 1)
    relative_36m = None
    if horizon >= 500:
        relative_36m = (close[-1] / close[-horizon - 1] - 1.0) - (
            benchmark_close[-1] / benchmark_close[-horizon - 1] - 1.0
        )
    long_window = close[-min(756, len(close)):]
    drawdown_3y = close[-1] / max(long_window) - 1.0
    momentum_12_1 = close[-22] / close[-253] - 1.0
    momentum_6m = _trailing_return(close, 126)
    sma200 = _mean(close[-200:])
    ma200_ratio = _ratio(close[-1], sma200)
    ma200_ratio = None if ma200_ratio is None else ma200_ratio - 1.0

    returns = [close[i] / close[i - 1] - 1.0 for i in range(max(1, len(close) - 252), len(close))]
    volatility_1y = statistics.stdev(returns) * math.sqrt(252) if len(returns) >= 20 else None

    price_votes = sum(bool(x) for x in (
        _finite(momentum_12_1) and momentum_12_1 > 0,
        _finite(momentum_6m) and momentum_6m > 0,
        _finite(ma200_ratio) and ma200_ratio > 0,
    ))
    return {
        "relative_36m": relative_36m,
        "drawdown_3y": drawdown_3y,
        "momentum_12_1": momentum_12_1,
        "momentum_6m": momentum_6m,
        "ma200_ratio": ma200_ratio,
        "volatility_1y": volatility_1y,
        "price_catalyst_votes": price_votes,
    }


def fundamental_features(fundamental, sector):
    periods = sorted(list(fundamental.get("periods") or []), key=lambda row: row.get("date", ""), reverse=True)
    market_cap = fundamental.get("market_cap")
    if len(periods) < 3 or not _finite(market_cap) or market_cap <= 0:
        return None
    rows = periods[:4]
    latest = rows[0]

    revenue = [row.get("revenue") for row in rows]
    revenue_growth_1y = None
    if len(revenue) >= 2 and _finite(revenue[0]) and _finite(revenue[1]) and revenue[1] > 0:
        revenue_growth_1y = revenue[0] / revenue[1] - 1.0

    equity = latest.get("equity")
    book_to_market = _ratio(equity, market_cap) if _finite(equity) and equity > 0 else None

    repurchases = latest.get("repurchases")
    issuance = latest.get("issuance")
    buyback_yield = abs(float(repurchases)) / market_cap if _finite(repurchases) and float(repurchases) != 0 else 0.0
    issuance_yield = abs(float(issuance)) / market_cap if _finite(issuance) and float(issuance) != 0 else 0.0

    if sector == "Financials":
        incomes = [row.get("net_income") for row in rows if _finite(row.get("net_income"))]
        if len(incomes) < 3:
            return None
        normalized_income = _median(incomes[:3])
        earnings_yield = _ratio(normalized_income, market_cap)
        positive_profit_years = sum(1 for value in incomes[:3] if value > 0)
        roe_values = []
        for row in rows[:3]:
            if _finite(row.get("net_income")) and _finite(row.get("equity")) and row["equity"] > 0:
                roe_values.append(row["net_income"] / row["equity"])
        normalized_roe = _median(roe_values)
        prior_income = _median(incomes[1:3]) if len(incomes) >= 3 else None
        earnings_acceleration = _ratio(incomes[0], prior_income)
        earnings_acceleration = None if earnings_acceleration is None else earnings_acceleration - 1.0
        fundamental_votes = sum(bool(x) for x in (
            _finite(revenue_growth_1y) and revenue_growth_1y > 0,
            _finite(earnings_acceleration) and earnings_acceleration > 0,
        ))
        return {
            "latest_statement_period": latest.get("date"),
            "financial_sector": True,
            "normalized_fcf_yield": None,
            "earnings_yield": earnings_yield,
            "book_to_market": book_to_market,
            "net_cash_to_market_cap": None,
            "fcf_margin": None,
            "operating_margin": None,
            "positive_fcf_years": None,
            "positive_profit_years": positive_profit_years,
            "normalized_roe": normalized_roe,
            "net_debt_to_ocf": None,
            "interest_coverage": None,
            "buyback_yield": buyback_yield,
            "issuance_yield": issuance_yield,
            "revenue_growth_1y": revenue_growth_1y,
            "fundamental_acceleration": earnings_acceleration,
            "fundamental_catalyst_votes": fundamental_votes,
            "profitability_latest": incomes[0],
        }

    required = ("revenue", "ocf", "capex")
    usable = [row for row in rows if all(_finite(row.get(key)) for key in required)]
    if len(usable) < 3:
        return None
    rows = usable
    latest = rows[0]

    fcfs, fcf_margins = [], []
    for row in rows:
        capex = abs(float(row["capex"]))
        fcf = float(row["ocf"]) - capex
        fcfs.append(fcf)
        if row["revenue"] > 0:
            fcf_margins.append(fcf / row["revenue"])
    normalized_fcf = _median(fcfs[:3])
    normalized_fcf_yield = _ratio(normalized_fcf, market_cap)
    positive_fcf_years = sum(1 for value in fcfs[:3] if value > 0)
    prior_fcf = _median(fcfs[1:3]) if len(fcfs) >= 3 else None
    fcf_acceleration = _ratio(fcfs[0], prior_fcf)
    fcf_acceleration = None if fcf_acceleration is None else fcf_acceleration - 1.0
    fcf_margin = _median(fcf_margins[:3])

    operating_income = latest.get("operating_income")
    operating_margin = _ratio(operating_income, latest["revenue"])
    debt = latest.get("debt")
    cash = latest.get("cash")
    net_cash_to_market_cap = None
    net_debt_to_ocf = None
    if _finite(cash) or _finite(debt):
        net_cash = (float(cash) if _finite(cash) else 0.0) - (float(debt) if _finite(debt) else 0.0)
        net_cash_to_market_cap = net_cash / market_cap
        net_debt = max(-net_cash, 0.0)
        if latest["ocf"] > 0:
            net_debt_to_ocf = net_debt / latest["ocf"]
        elif net_debt > 0:
            net_debt_to_ocf = math.inf

    interest = latest.get("interest_expense")
    if _finite(interest) and abs(float(interest)) > 1e-9 and _finite(operating_income):
        interest_coverage = float(operating_income) / abs(float(interest))
    elif _finite(debt) and float(debt) <= 0:
        interest_coverage = 100.0
    else:
        interest_coverage = None

    fundamental_votes = sum(bool(x) for x in (
        _finite(revenue_growth_1y) and revenue_growth_1y > 0,
        _finite(fcf_acceleration) and fcf_acceleration > 0,
    ))
    return {
        "latest_statement_period": latest.get("date"),
        "financial_sector": False,
        "normalized_fcf_yield": normalized_fcf_yield,
        "earnings_yield": None,
        "book_to_market": book_to_market,
        "net_cash_to_market_cap": net_cash_to_market_cap,
        "fcf_margin": fcf_margin,
        "operating_margin": operating_margin,
        "positive_fcf_years": positive_fcf_years,
        "positive_profit_years": None,
        "normalized_roe": None,
        "net_debt_to_ocf": net_debt_to_ocf,
        "interest_coverage": interest_coverage,
        "buyback_yield": buyback_yield,
        "issuance_yield": issuance_yield,
        "revenue_growth_1y": revenue_growth_1y,
        "fundamental_acceleration": fcf_acceleration,
        "fundamental_catalyst_votes": fundamental_votes,
        "profitability_latest": fcfs[0],
    }


def score_universe(raw_candidates, config):
    model = config["model"]
    rows = []
    for raw in raw_candidates:
        pf = price_features(raw["close"], raw["benchmark_close"])
        ff = fundamental_features(raw["fundamental"], raw["sector"])
        if pf is None or ff is None:
            continue
        rows.append({"ticker": raw["ticker"], "sector": raw["sector"], **pf, **ff})

    if not rows:
        return []

    by_sector = defaultdict(list)
    for row in rows:
        by_sector[row["sector"]].append(row)

    metric_names = (
        "normalized_fcf_yield", "earnings_yield", "book_to_market", "net_cash_to_market_cap",
        "fcf_margin", "operating_margin", "positive_fcf_years", "positive_profit_years",
        "normalized_roe", "net_debt_to_ocf", "interest_coverage", "buyback_yield",
        "issuance_yield", "relative_36m", "drawdown_3y"
    )

    for sector, peers in by_sector.items():
        metrics = {key: [row.get(key) for row in peers] for key in metric_names}
        for row in peers:
            if row["financial_sector"]:
                valuation_score = _weighted_average([
                    (_pct_rank(metrics["earnings_yield"], row["earnings_yield"], higher_better=True), 0.45),
                    (_pct_rank(metrics["book_to_market"], row["book_to_market"], higher_better=True), 0.55),
                ])
                quality_score = _weighted_average([
                    (_pct_rank(metrics["normalized_roe"], row["normalized_roe"], higher_better=True), 0.45),
                    (_pct_rank(metrics["positive_profit_years"], row["positive_profit_years"], higher_better=True), 0.35),
                    (_pct_rank([x.get("revenue_growth_1y") for x in peers], row["revenue_growth_1y"], higher_better=True), 0.20),
                ])
                survival_gate = bool(
                    row["positive_profit_years"] is not None and row["positive_profit_years"] >= 2 and
                    _finite(row["profitability_latest"]) and row["profitability_latest"] > 0
                )
            else:
                valuation_score = _weighted_average([
                    (_pct_rank(metrics["normalized_fcf_yield"], row["normalized_fcf_yield"], higher_better=True), 0.50),
                    (_pct_rank(metrics["net_cash_to_market_cap"], row["net_cash_to_market_cap"], higher_better=True), 0.25),
                    (_pct_rank(metrics["book_to_market"], row["book_to_market"], higher_better=True), 0.25),
                ])
                quality_score = _weighted_average([
                    (_pct_rank(metrics["fcf_margin"], row["fcf_margin"], higher_better=True), 0.25),
                    (_pct_rank(metrics["positive_fcf_years"], row["positive_fcf_years"], higher_better=True), 0.20),
                    (_pct_rank(metrics["operating_margin"], row["operating_margin"], higher_better=True), 0.20),
                    (_pct_rank(metrics["net_debt_to_ocf"], row["net_debt_to_ocf"], higher_better=False), 0.20),
                    (_pct_rank(metrics["interest_coverage"], row["interest_coverage"], higher_better=True), 0.15),
                ])
                debt_ok = (not _finite(row["net_debt_to_ocf"]) or
                           row["net_debt_to_ocf"] <= model["maximum_net_debt_to_ocf"])
                coverage_ok = (not _finite(row["interest_coverage"]) or
                               row["interest_coverage"] >= model["minimum_interest_coverage"])
                survival_gate = bool(
                    row["positive_fcf_years"] is not None and
                    row["positive_fcf_years"] >= model["minimum_positive_fcf_years"] and
                    _finite(row["profitability_latest"]) and row["profitability_latest"] > 0 and
                    debt_ok and coverage_ok
                )

            capital_allocation_score = _weighted_average([
                (_pct_rank(metrics["buyback_yield"], row["buyback_yield"], higher_better=True), 0.45),
                (_pct_rank(metrics["issuance_yield"], row["issuance_yield"], higher_better=False), 0.30),
                (_pct_rank(metrics["net_cash_to_market_cap"], row["net_cash_to_market_cap"], higher_better=True), 0.25),
            ])
            if capital_allocation_score is None:
                capital_allocation_score = _weighted_average([
                    (_pct_rank(metrics["buyback_yield"], row["buyback_yield"], higher_better=True), 0.60),
                    (_pct_rank(metrics["issuance_yield"], row["issuance_yield"], higher_better=False), 0.40),
                ])

            dislocation_score = _weighted_average([
                (_pct_rank(metrics["relative_36m"], row["relative_36m"], higher_better=False), 0.55),
                (_pct_rank(metrics["drawdown_3y"], row["drawdown_3y"], higher_better=False), 0.45),
            ])
            catalyst_votes = int(row["price_catalyst_votes"] + row["fundamental_catalyst_votes"])
            catalyst_score = 100.0 * catalyst_votes / 5.0

            weights = model["weights"]
            composite_score = _weighted_average([
                (valuation_score, weights["valuation"]),
                (quality_score, weights["quality"]),
                (capital_allocation_score, weights["capital_allocation"]),
                (dislocation_score, weights["dislocation"]),
                (catalyst_score, weights["catalyst"]),
            ])

            row.update(
                valuation_score=valuation_score,
                quality_score=quality_score,
                capital_allocation_score=capital_allocation_score,
                dislocation_score=dislocation_score,
                catalyst_votes=catalyst_votes,
                catalyst_score=catalyst_score,
                composite_score=composite_score,
                survival_gate=survival_gate,
            )
            opportunity_gate = (
                (_finite(dislocation_score) and dislocation_score >= model["minimum_dislocation_score"]) or
                (_finite(valuation_score) and valuation_score >= 70.0)
            )
            row["entry_eligible"] = bool(
                survival_gate and opportunity_gate and
                _finite(valuation_score) and valuation_score >= model["minimum_valuation_score"] and
                _finite(quality_score) and quality_score >= model["minimum_quality_score"] and
                catalyst_votes >= model["minimum_catalyst_votes"] and
                _finite(composite_score) and composite_score >= model["entry_score"]
            )
            row["hard_exit"] = bool(
                not survival_gate or
                (_finite(composite_score) and composite_score < model["hard_exit_score"])
            )
            row["rerated"] = bool(
                _finite(valuation_score) and valuation_score < model["rerated_valuation_score"] and
                _finite(dislocation_score) and dislocation_score < model["rerated_dislocation_score"]
            )

    return sorted(
        rows,
        key=lambda x: (-(x["composite_score"] if _finite(x["composite_score"]) else -math.inf), x["ticker"])
    )


def months_between(start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return (b.year - a.year) * 12 + b.month - a.month


def _invest_fraction(eligible_count, model):
    schedule = sorted(model["invest_fraction_by_eligible"], key=lambda x: -int(x["min_candidates"]))
    for item in schedule:
        if eligible_count >= int(item["min_candidates"]):
            return float(item["invest_fraction"])
    return 0.0


def _allocate(selected_rows, invest_fraction, policy):
    if not selected_rows or invest_fraction <= 0:
        return {}
    raw = {}
    for row in selected_rows:
        score = max(float(row.get("composite_score") or 0.0), 1.0) / 100.0
        vol = float(row.get("volatility_1y")) if _finite(row.get("volatility_1y")) else 0.35
        raw[row["ticker"]] = (score ** 2) / math.sqrt(max(vol, 0.12))
    total = sum(raw.values())
    if total <= 0:
        return {}
    weights = {
        ticker: min(invest_fraction * value / total, float(policy["max_position_weight"]))
        for ticker, value in raw.items()
    }

    # Scale sector groups to their explicit risk cap; unallocated capital remains cash.
    by_sector = defaultdict(list)
    row_lookup = {row["ticker"]: row for row in selected_rows}
    for ticker in weights:
        by_sector[row_lookup[ticker]["sector"]].append(ticker)
    for tickers in by_sector.values():
        sector_weight = sum(weights[ticker] for ticker in tickers)
        cap = float(policy["max_sector_weight"])
        if sector_weight > cap and sector_weight > 0:
            scale = cap / sector_weight
            for ticker in tickers:
                weights[ticker] *= scale
    return {ticker: weight for ticker, weight in weights.items() if weight > 0}


def choose_portfolio(scored, positions, asof, config):
    """Concentrated, catalyst-aware rotation with explicit cash when ideas are scarce."""
    model, policy = config["model"], config["paper_policy"]
    lookup = {row["ticker"]: row for row in scored}
    exits = {}
    candidates = []

    for row in scored:
        ticker = row["ticker"]
        position = (positions or {}).get(ticker)
        held = months_between(position["entry_date"], asof) if position else None
        if position:
            if row["hard_exit"]:
                exits[ticker] = "hard_quality_or_value_exit"
                continue
            if held >= model["minimum_hold_months"] and row["rerated"]:
                exits[ticker] = "valuation_rerated"
                continue
            if held >= model["minimum_hold_months"] and (
                not _finite(row["composite_score"]) or row["composite_score"] < model["retention_score"]
            ):
                exits[ticker] = "score_below_retention"
                continue
            # Small hysteresis bonus avoids needless monthly turnover while still
            # allowing a clearly better opportunity to replace an incumbent.
            candidates.append((float(row["composite_score"]) + 4.0, row, True))
        elif row["entry_eligible"]:
            candidates.append((float(row["composite_score"]), row, False))

    candidates.sort(key=lambda item: (-item[0], item[1]["ticker"]))
    selected = []
    sector_counts = defaultdict(int)
    for _, row, _ in candidates:
        if len(selected) >= int(policy["max_positions"]):
            break
        if sector_counts[row["sector"]] >= int(policy["max_sector_positions"]):
            continue
        selected.append(row)
        sector_counts[row["sector"]] += 1

    selected_tickers = {row["ticker"] for row in selected}
    for ticker, position in sorted((positions or {}).items()):
        if ticker in exits or ticker in selected_tickers:
            continue
        row = lookup.get(ticker)
        if row is None:
            exits[ticker] = "data_missing"
            continue
        held = months_between(position["entry_date"], asof)
        exits[ticker] = "rank_replaced" if held >= model["minimum_hold_months"] else "sector_or_position_cap"

    eligible_count = sum(bool(row.get("entry_eligible")) for row in scored)
    invest_fraction = _invest_fraction(eligible_count, model)
    return _allocate(selected, invest_fraction, policy), exits, invest_fraction
