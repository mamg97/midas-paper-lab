import json
import unittest

from publish_snapshot import build_payload


class SnapshotTests(unittest.TestCase):
    def test_exports_only_dated_demo_equity(self):
        raw = json.dumps({"initial_capital": 100000, "cash": 80000,
                          "positions": {"PRIVATE": {"shares": 2}},
                          "history": [{"ticker": "PRIVATE"}],
                          "equity_history": {"2026-02-27": 99900, "2026-03-02": 100200}}).encode()
        payload = build_payload(raw)
        self.assertEqual(payload["equity_history"], [["2026-02-27", 99900.0], ["2026-03-02", 100200.0]])
        self.assertNotIn("PRIVATE", json.dumps(payload))
        self.assertNotIn("positions", payload)

    def test_archive_uses_separate_private_id_and_rejects_fake_history(self):
        raw = json.dumps({"schema_version": 1, "model": "next_open_raw_ohlc_v1",
                          "initial_capital": 100000, "last_session": "2026-10-07",
                          "positions": {"SECRET": {"shares": 4}},
                          "equity_history": {"2026-09-29": 100000,
                                             "2026-10-07": 101008}}).encode()
        archive = build_payload(raw, "genetic_sp500_forward_archive")
        self.assertEqual(archive["strategy_id"], "genetic_sp500_forward_archive")
        self.assertEqual(archive["quality"], "next_open_raw_ohlc_v1")
        self.assertEqual(archive["equity_history"][-1], ["2026-10-07", 101008.0])
        self.assertNotIn("SECRET", json.dumps(archive))
        self.assertNotIn("SECRET", json.dumps(build_payload(raw, "genetic_sp500_forward")))

    def test_rejects_invalid_equity(self):
        raw = json.dumps({"initial_capital": 100000,
                          "equity_history": {"2026-02-27": 99900, "2026-03-02": -1}}).encode()
        with self.assertRaisesRegex(ValueError, "Patrimonio inválido"):
            build_payload(raw)

    def test_forward_exports_first_completed_session_without_positions(self):
        raw = json.dumps({"schema_version": 1, "model": "next_open_raw_ohlc_v1",
                          "initial_capital": 100000, "last_session": "2026-09-28",
                          "positions": {"SECRET": {"shares": 10}},
                          "equity_history": {"2026-09-28": 100000}}).encode()
        payload = build_payload(raw, "genetic_sp500_forward")
        self.assertEqual(payload["strategy_id"], "genetic_sp500_forward")
        self.assertEqual(payload["quality"], "next_open_raw_ohlc_v1")
        self.assertNotIn("SECRET", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
