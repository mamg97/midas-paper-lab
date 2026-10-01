import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_corpus


class CorpusTests(unittest.TestCase):
    def test_vtt_parser_removes_timing_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.vtt"
            path.write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHola mundo\n"
                "00:00:02.000 --> 00:00:04.000\nHola mundo\n"
                "00:00:04.000 --> 00:00:06.000\n<font color=\"red\">Deuda y caja</font>\n",
                encoding="utf-8",
            )
            text = build_corpus._parse_vtt(path)
            self.assertEqual(text, "Hola mundo Deuda y caja")
            self.assertNotIn("-->", text)

    def test_lexicon_counts_are_derived_not_transcript_storage(self):
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        counts = build_corpus._lexicon_counts(
            "Buscamos calidad, flujo de caja libre y poca deuda. La valoración importa.",
            config["strategy_lexicons"],
        )
        self.assertGreater(counts["quality"]["count"], 0)
        self.assertGreater(counts["cash_flow"]["count"], 0)
        self.assertGreater(counts["balance_sheet"]["count"], 0)
        self.assertGreater(counts["valuation"]["count"], 0)

    def test_categories_prioritize_methodology_and_portfolio(self):
        self.assertEqual(
            build_corpus._category("Cómo buscar, analizar e INVERTIR en EMPRESAS", "long"),
            "methodology",
        )
        self.assertEqual(
            build_corpus._category("Nuestra CARTERA de INVERSIÓN en SEPTIEMBRE", "long"),
            "portfolio_update",
        )
        self.assertEqual(build_corpus._category("Un Short cualquiera", "short"), "short")

    def test_guest_penalty_applies(self):
        base = {
            "word_count": 1000,
            "category": "methodology",
            "guest_likely": False,
            "lexicon_counts": {k: {"count": 3, "terms": {}} for k in [
                "quality","cash_flow","valuation","balance_sheet","capital_allocation",
                "contrarian","cyclical","portfolio","entry","exit","risk","technical",
                "management","macro"
            ]},
        }
        clean = build_corpus._relevance(base)
        guest = build_corpus._relevance({**base, "guest_likely": True})
        self.assertGreater(clean, guest)


    def test_diagnostics_keep_errors_but_redact_urls(self):
        lines = build_corpus._diagnostic_lines(
            "WARNING: subtitles unavailable at https://example.com/signed?x=1\n"
            "INFO: harmless\nERROR: HTTP 403 blocked"
        )
        self.assertEqual(len(lines), 2)
        self.assertIn("<url>", lines[0])
        self.assertNotIn("example.com", lines[0])
        self.assertIn("403", lines[1])

    def test_canary_failure_stops_before_full_channel_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                build_corpus,
                "_caption_command",
                return_value={"returncode": 0, "timed_out": False, "messages": ["blocked"]},
            ) as call:
                result = build_corpus._download_captions(
                    "https://www.youtube.com/@Buy_The_Dip",
                    tmp,
                    ["es"],
                    canary_video_id="abc123",
                    sleep_seconds=0,
                )
        self.assertEqual(result["status"], "blocked_or_unavailable")
        self.assertFalse(result["canary_ok"])
        self.assertEqual(call.call_count, 1)

    def test_canary_success_allows_surface_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fake_command(url, temp_dir, langs, **kwargs):
                if "watch?v=abc123" in url:
                    Path(temp_dir, "abc123.es.vtt").write_text(
                        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHola",
                        encoding="utf-8",
                    )
                return {"returncode": 0, "timed_out": False, "messages": []}
            with mock.patch.object(build_corpus, "_caption_command", side_effect=fake_command) as call:
                result = build_corpus._download_captions(
                    "https://www.youtube.com/@Buy_The_Dip",
                    tmp,
                    ["es"],
                    canary_video_id="abc123",
                    sleep_seconds=0,
                )
        self.assertEqual(result["status"], "reachable")
        self.assertTrue(result["canary_ok"])
        self.assertEqual(call.call_count, 1 + len(build_corpus.SURFACES))


if __name__ == "__main__":
    unittest.main()
