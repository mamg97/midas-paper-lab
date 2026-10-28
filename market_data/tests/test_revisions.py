import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_data import collect
from market_data.consume import overlay
from market_data.revisions import append_missing, load_effective, revision_dir
from market_data.snapshot import _digest, make_snapshot, write_immutable

DAY = "2026-10-27"
STAMP = "2026-10-28T01:00:00+00:00"
NAMES = [f"S{i:03d}" for i in range(503)]


def row():
    return {"date": DAY, "open": 100., "high": 103., "low": 99., "close": 102.,
            "volume": 500., "dividend": 0., "split": 0.}


class MissingRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = make_snapshot(DAY, NAMES, {"SPY": row()}, captured_at_utc=STAMP)
        self.path, _ = write_immutable(self.root, self.base)
        self.original = self.path.read_bytes()

    def test_chain_adds_only_missing_data_without_rewriting_base(self):
        _, first = append_missing(self.root, DAY, {NAMES[0]: row()}, captured_at_utc=STAMP)
        _, second = append_missing(self.root, DAY, {NAMES[1]: row()}, captured_at_utc=STAMP)
        self.assertEqual(second["parent_sha256"], first["sha256"])
        got = load_effective(self.root, DAY)
        self.assertEqual(got["revision_hashes"], [first["sha256"], second["sha256"]])
        self.assertEqual(got["effective_sha256"], second["sha256"])
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(len(got["missing"]), 501)
        bars, info = overlay(DAY, {}, self.root)
        self.assertEqual(bars[NAMES[1]]["close"], 102.)
        self.assertEqual(info["hash"], self.base["sha256"])
        self.assertEqual(info["effective_sha256"], second["sha256"])

    def test_existing_quote_wrong_date_or_corporate_action_never_overwritten(self):
        for observations in [{"SPY": row()}, {NAMES[0]: {**row(), "date": "2026-10-26"}},
                             {NAMES[0]: {**row(), "split": 2}}, {NAMES[0]: {**row(), "dividend": .5}}]:
            with self.assertRaises(ValueError):
                append_missing(self.root, DAY, observations, captured_at_utc=STAMP)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(list(revision_dir(self.root, DAY).glob("*.json")))

    def test_tampered_revision_fails_closed(self):
        path, item = append_missing(self.root, DAY, {NAMES[0]: row()}, captured_at_utc=STAMP)
        item["bars"][NAMES[0]]["close"] = 101.
        path.write_text(json.dumps(item))
        got, info = overlay(DAY, {}, self.root)
        self.assertEqual(got, {})
        self.assertEqual(info["status"], "snapshot_rejected")

    def test_unlinked_or_ambiguous_branch_is_rejected(self):
        _, first = append_missing(self.root, DAY, {NAMES[0]: row()}, captured_at_utc=STAMP)
        rogue = copy.deepcopy(first)
        rogue["bars"] = {NAMES[1]: first["bars"][NAMES[0]].copy()}
        rogue["sha256"] = _digest(rogue)
        (revision_dir(self.root, DAY) / (rogue["sha256"] + ".json")).write_text(json.dumps(rogue))
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            load_effective(self.root, DAY)

    def test_collector_recovers_only_missing_symbols_and_is_idempotent(self):
        with (patch.object(collect, "calendar", return_value=(DAY, None, None, False)),
              patch.object(collect, "ROOT", self.root.parent),
              patch.object(collect, "SNAPSHOTS", self.root),
              patch.object(collect, "collect", return_value=({NAMES[0]: row()}, {})) as provider):
            result = collect.recover_missing()
        self.assertEqual(provider.call_args.args, (DAY, NAMES))
        self.assertFalse(provider.call_args.kwargs["include_benchmark"])
        self.assertEqual(result["recovered"], [NAMES[0]])
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertNotIn(NAMES[0], load_effective(self.root, DAY)["missing"])
