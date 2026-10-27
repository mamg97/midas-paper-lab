"""Shared raw Yahoo download fault isolation, deterministic/offline."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run


class SharedYahooBatchTests(unittest.TestCase):
    def test_one_bad_symbol_does_not_drop_rest_of_forty(self):
        symbols = ["BAD"] + [f"S{i:03}" for i in range(39)]
        calls = []

        def download(batch, **kwargs):
            calls.append(tuple(batch))
            if "BAD" in batch and len(batch) > 1:
                raise ConnectionError("one symbol poisoned vendor batch")
            return {ticker: object() for ticker in batch if ticker != "BAD"}

        with patch.dict(sys.modules, {"yfinance": SimpleNamespace(download=download)}):
            with patch.object(run, "_series", side_effect=lambda raw, ticker: raw[ticker]):
                observed = run._download(symbols, "2026-10-01", "2026-10-27",
                                         allow_missing=True)
        self.assertEqual(set(observed), set(symbols) - {"BAD"})
        self.assertGreater(len(calls), 1)
        self.assertLessEqual(len(calls), 1 + 24)
        # The failed ticker has no synthetic price, even after retry.
        self.assertNotIn("BAD", observed)

    def test_vendor_outage_is_bounded_and_does_not_invent_frames(self):
        symbols = [f"S{i:03}" for i in range(503)]
        calls = []

        def outage(batch, **kwargs):
            calls.append(tuple(batch))
            raise ConnectionError("vendor unavailable")

        with patch.dict(sys.modules, {"yfinance": SimpleNamespace(download=outage)}):
            observed = run._download(symbols, "2026-10-01", "2026-10-27",
                                     allow_missing=True)
        self.assertEqual(observed, {})
        # Thirteen 40-symbol batches plus at most twenty-four retries.
        self.assertLessEqual(len(calls), 13 + 24)
        self.assertEqual(len(set(symbols)), 503)

    def test_strict_mode_still_fails_closed(self):
        calls = []

        def outage(batch, **kwargs):
            calls.append(tuple(batch))
            raise ConnectionError("do not misstate mandatory marks")

        with patch.dict(sys.modules, {"yfinance": SimpleNamespace(download=outage)}):
            with self.assertRaises(ConnectionError):
                run._download(["AAPL", "SPY"], "2026-10-01", "2026-10-27",
                              allow_missing=False)
        self.assertEqual(len(calls), 1)

    def test_partial_vendor_response_retains_good_symbols(self):
        with patch.dict(sys.modules, {"yfinance": SimpleNamespace(
            download=lambda batch, **kwargs: {"AAPL": object()}
        )}):
            with patch.object(run, "_series", side_effect=lambda raw, ticker: raw[ticker]):
                frames = run._download(["AAPL", "BAD"], "2026-10-01",
                                       "2026-10-27", allow_missing=True)
        self.assertEqual(set(frames), {"AAPL"})


if __name__ == "__main__":
    unittest.main()
