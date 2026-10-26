"""Deterministic import-order regression tests; synthetic, isolated data only."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import harness_core as core


class ImportOrderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = core.Store(self.root / "source")
        self.dest = core.Store(self.root / "destination")

    def records(self, ids):
        data = core.blank()
        data["candidates"] = [{"id": "candidate", "rule": "synthetic rule",
            "context": "portrait", "model": "*", "model_version": "*", "evidence": [],
            "goal": "synthetic goal", "factor": "contact", "status": "rejected",
            "fingerprint": "synthetic", "time": "2026-10-26T00:00:00+00:00"}]
        data["experiments"] = [{"id": value, "candidate_id": "candidate", "pairs": [],
            "criteria": "criterion for " + value, "passed": False, "level": "text",
            "time": "2026-10-26T00:00:00+00:00"} for value in ids]
        return data

    def merge(self, existing, incoming):
        self.source.change(lambda data: data.update(self.records(incoming)))
        self.dest.change(lambda data: data.update(self.records(existing)))
        path = self.root / "migration.zip"
        core.export_data(self.source, path)
        result = core.import_data(self.dest, path)
        expected = {e["id"]: e for e in self.records(existing + incoming)["experiments"]}
        actual = {e["id"]: e for e in self.dest.load()["experiments"]}
        self.assertEqual(actual, expected)
        self.assertEqual(result["added"]["experiments"], len(set(incoming) - set(existing)))
        self.assertFalse(self.dest.load()["config"]["enabled"])
        return path

    def test_reverse_uuid_merge(self):
        self.merge(["f" * 32], ["a" * 32, "f" * 32])

    def test_ascending_uuid_merge(self):
        self.merge(["a" * 32], ["a" * 32, "f" * 32])

    def test_interleaved_multiple_records(self):
        self.merge(["c" * 32, "f" * 32], ["a" * 32, "d" * 32, "f" * 32])

    def test_repeat_import_deduplicates(self):
        path = self.merge(["f" * 32], ["a" * 32, "f" * 32])
        again = core.import_data(self.dest, path)
        self.assertEqual(again["added"]["experiments"], 0)
        self.assertEqual(len(self.dest.load()["experiments"]), 2)

    def test_reordered_experiments_only_are_equal(self):
        expected = self.records(["f" * 32, "a" * 32])
        actual = copy.deepcopy(expected)
        actual["experiments"].reverse()
        core.verify_imported_data(expected, actual)
        self.assertEqual(expected["experiments"][0]["id"], "f" * 32)

    def test_missing_duplicate_and_changed_records_rejected(self):
        expected = self.records(["f" * 32, "a" * 32])
        for fault in ("missing", "duplicate", "changed", "extra"):
            with self.subTest(fault=fault):
                actual = copy.deepcopy(expected)
                if fault == "missing":
                    actual["experiments"].pop()
                elif fault == "duplicate":
                    actual["experiments"].append(copy.deepcopy(actual["experiments"][0]))
                elif fault == "changed":
                    actual["experiments"][0]["criteria"] = "corrupted"
                else:
                    actual["experiments"] += self.records(["b" * 32])["experiments"]
                with self.assertRaises(core.HarnessError):
                    core.verify_imported_data(expected, actual)

    def test_other_data_and_log_order_still_checked(self):
        expected = self.records(["f" * 32])
        core.log_event(expected, "first", None, None, "first reason")
        core.log_event(expected, "second", None, None, "second reason")
        for fault in ("config", "log_order"):
            with self.subTest(fault=fault):
                actual = copy.deepcopy(expected)
                if fault == "config":
                    actual["config"]["enabled"] = True
                else:
                    actual["evolution_log"].reverse()
                with self.assertRaises(core.HarnessError):
                    core.verify_imported_data(expected, actual)

    def test_import_still_detects_persisted_content_corruption(self):
        self.source.change(lambda data: data.update(self.records(["a" * 32])))
        path = self.root / "migration.zip"
        core.export_data(self.source, path)
        original_save = core.Store.save
        def corrupted_save(store, data):
            if store.root == self.dest.root and data["experiments"]:
                data = copy.deepcopy(data)
                data["experiments"][0]["criteria"] = "simulated corrupted content"
            return original_save(store, data)
        with patch.object(core.Store, "save", corrupted_save):
            with self.assertRaisesRegex(core.HarnessError, "导入后数据核验失败"):
                core.import_data(self.dest, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
