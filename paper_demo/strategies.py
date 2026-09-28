"""Versioned daily-close signals for the MIDAS paper portfolios.

These are explicit new variants inspired by historical work, not claims of
bit-for-bit equivalence with the original R/Python experiments.
"""

from math import sqrt


def ema(values, period):
    alpha = 2 / (period + 1)
    out = []
    for value in values:
        out.append(value if not out else alpha * value + (1 - alpha) * out[-1])
    return out


def rsi(values, period):
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(x, 0) for x in changes[:period]) / period
    loss = sum(max(-x, 0) for x in changes[:period]) / period
    for change in changes[period:]:
        gain = (gain * (period - 1) + max(change, 0)) / period
        loss = (loss * (period - 1) + max(-change, 0)) / period
    return 50 if gain == loss == 0 else 100 if loss == 0 else 100 - 100 / (1 + gain / loss)


def _cross_up(previous_a, previous_b, current_a, current_b):
    return previous_a <= previous_b and current_a > current_b


def _cross_down(previous_a, previous_b, current_a, current_b):
    return previous_a >= previous_b and current_a < current_b


def signal(kind, bars, params):
    """Return buy/sell/hold using only bars available through today's close."""
    close = [bar["close"] for bar in bars]
    if kind == "equal_weight_hold":
        return "buy"
    if kind in ("ema_rsi", "genetic_frozen"):
        fast, slow = int(params["fast"]), int(params["slow"])
        period = int(params["rsi_period"])
        minimum = max(slow, period + 1) if kind == "genetic_frozen" else max(slow * 3, period + 2)
        if len(close) < minimum:
            return "hold"
        a, b = ema(close, fast), ema(close, slow)
        strength = rsi(close, period)
        if strength < params["oversold"]:
            return "sell"
        crossed = (a[-2] < b[-2] and a[-1] >= b[-1]) if kind == "genetic_frozen" else _cross_up(a[-2], b[-2], a[-1], b[-1])
        if crossed and strength < params["overbought"]:
            return "buy"
        return "hold"
    if kind == "macd":
        if len(close) < 78:
            return "hold"
        fast, slow = ema(close, 12), ema(close, 26)
        macd = [a - b for a, b in zip(fast, slow)]
        line = ema(macd, 9)
        if _cross_up(macd[-2], line[-2], macd[-1], line[-1]):
            return "buy"
        if _cross_down(macd[-2], line[-2], macd[-1], line[-1]):
            return "sell"
        return "hold"
    if kind == "rsi_reversion":
        if len(close) < 30:
            return "hold"
        previous, current = rsi(close[:-1], 14), rsi(close, 14)
        return "buy" if previous >= 30 > current else "sell" if previous <= 55 < current else "hold"
    if kind == "bollinger_breakout":
        if len(close) < 21:
            return "hold"

        def bands(values):
            window = values[-20:]
            mean = sum(window) / 20
            deviation = sqrt(sum((x - mean) ** 2 for x in window) / 20)
            return mean, mean + 2 * deviation

        old_mid, old_upper = bands(close[:-1])
        mid, upper = bands(close)
        return ("buy" if _cross_up(close[-2], old_upper, close[-1], upper)
                else "sell" if _cross_down(close[-2], old_mid, close[-1], mid) else "hold")
    if kind in ("turtle_20_10", "turtle_55_20"):
        entry = 20 if kind == "turtle_20_10" else 55
        exit_window = 10 if kind == "turtle_20_10" else 20
        if len(bars) < entry + 2:
            return "hold"
        prior_high = max(bar["high"] for bar in bars[-entry - 1:-1])
        prior_low = min(bar["low"] for bar in bars[-exit_window - 1:-1])
        return "buy" if close[-1] > prior_high else "sell" if close[-1] < prior_low else "hold"
    raise ValueError("Estrategia desconocida: " + kind)
