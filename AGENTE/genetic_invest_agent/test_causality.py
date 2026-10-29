"""Causal indicators and post-session vendor data must not change a signal."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import sp500_portfolio_agent as agent


class CausalityTests(unittest.TestCase):
    def test_indicators_do_not_read_future_prices(self):
        index = pd.bdate_range("2026-01-01", periods=180)
        prices = 100 + np.arange(180) * .1 + np.sin(np.arange(180))
        frame = pd.DataFrame({"Open": prices, "High": prices+1, "Low": prices-1,
                              "Close": prices, "Volume": 10000}, index=index)
        genes = {"fast_ma": 5, "slow_ma": 20, "rsi_period": 7,
                 "rsi_overbought": 80, "rsi_oversold": 20,
                 "stop_loss_pct": .05, "take_profit_pct": .10}
        prefix = agent.compute_indicators(frame.iloc[:150], genes)
        whole = agent.compute_indicators(frame, genes)
        pd.testing.assert_frame_equal(prefix, whole.loc[prefix.index])

    def test_signals_refuse_bars_after_the_named_session(self):
        frame = pd.DataFrame({"Close": np.arange(30)+100}, index=pd.bdate_range("2026-10-01", periods=30))
        genome = agent.Genome()
        with patch.object(agent, "download_all", return_value={"TEST": frame}), \
                patch.object(agent, "compute_indicators") as indicators:
            self.assertEqual(agent.generate_live_signals(genome, end_date="2026-12-01", signal_session="2026-10-28"), ([], [], []))
            indicators.assert_not_called()
