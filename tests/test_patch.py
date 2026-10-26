"""Regression cases for 1.2.1; synthetic data and isolated stores only."""
import copy
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import harness_core as core


class PatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = core.Store(self.root / "data")

    def feedback(self, **changes):
        args = dict(prompt_id="p1", rating="喜欢", raw="以后用冷色",
                    features=["冷色"], confirmed=True, long_term=True,
                    context="肖像", model="M", model_version="未知")
        args.update(changes)
        return self.store.feedback(**args)

    def test_unknown_version_is_not_wildcard(self):
        self.feedback()
        self.assertEqual(self.store.applicable("肖像", "M", "v2")["preferences"], [])
        self.assertEqual(len(self.store.applicable("肖像", "M")["preferences"]), 1)

    def test_explicit_wildcard_still_matches(self):
        self.feedback(model_version="*")
        self.assertEqual(len(self.store.applicable("肖像", "M", "v2")["preferences"]), 1)

    def test_feedback_flags_require_real_booleans(self):
        for key in ("confirmed", "permanent", "hard_confirmed", "long_term", "cross_model"):
            for value in ("false", 1, None):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(core.HarnessError):
                        self.feedback(**{key: value})
        self.assertEqual(self.store.load()["user_preferences"]["feedback"], [])

    def test_first_save_failure_can_retry(self):
        original = core.atomic
        def fail_pointer(path, raw):
            if Path(path).name == "CURRENT":
                raise OSError("simulated publication failure")
            return original(path, raw)
        with patch.object(core, "atomic", fail_pointer):
            self.assertFalse(self.store.probe(create=True)["available"])
        self.assertTrue(self.store.probe(create=True)["available"])

    def test_nonempty_orphan_generation_still_rejected(self):
        (self.store.root / "generations" / "orphan").mkdir(parents=True)
        self.assertFalse(self.store.probe()["available"])

    def test_infinite_regression_tolerance_rejected(self):
        with self.assertRaises(core.HarnessError):
            self.store.configure({"max_regression": float("inf")})

    def test_import_conflicting_feedback_does_not_rebind_preference(self):
        self.feedback()
        incoming = copy.deepcopy(self.store.load()["user_preferences"])
        incoming["feedback"][0]["raw"] = "different evidence"
        incoming["preferences"][0]["id"] = "new-preference"
        incoming["preferences"][0]["content"] = "暖色"
        path = self.root / "preferences.json"
        path.write_bytes(core.encoded(incoming))
        result = core.import_data(self.store, path)
        self.assertEqual(result["added"]["preferences"], 0)
        self.assertTrue(any(c["category"] == "preferences" for c in result["conflicts"]))

    def experiment_data(self):
        self.feedback()
        data = self.store.load()
        data["candidates"] = [dict(id="candidate", rule="rule", context="肖像", model="M",
            model_version="v1", evidence=[data["user_preferences"]["feedback"][0]["id"]],
            goal="goal", factor="factor", status="rejected", fingerprint="fingerprint", time="time")]
        data["experiments"] = [dict(id=name, candidate_id="candidate", pairs=[], criteria="criteria",
            passed=False, level="text", time="time") for name in ("z-last", "a-first")]
        return data

    def test_import_experiment_order_is_stable(self):
        data = self.experiment_data()
        self.store.change(lambda target: target.update(data))
        archive = self.root / "full.zip"
        core.export_data(self.store, archive)
        dest = core.Store(self.root / "dest")
        partial = copy.deepcopy(data)
        partial["experiments"] = [data["experiments"][0]]
        dest.change(lambda target: target.update(partial))
        core.import_data(dest, archive)
        self.assertEqual([e["id"] for e in dest.load()["experiments"]], ["a-first", "z-last"])

    def test_feedback_conflict_blocks_derived_experiment_chain(self):
        data = self.experiment_data()
        self.store.change(lambda target: target.update(data))
        archive = self.root / "full.zip"
        core.export_data(self.store, archive)
        dest = core.Store(self.root / "dest")
        def local(target):
            target["user_preferences"] = copy.deepcopy(data["user_preferences"])
            target["user_preferences"]["feedback"][0]["raw"] = "local correction"
        dest.change(local)
        result = core.import_data(dest, archive)
        self.assertEqual(dest.load()["candidates"], [])
        self.assertEqual(dest.load()["experiments"], [])
        self.assertTrue(any(c["category"] == "experiments" for c in result["conflicts"]))

    def archive_version(self, version, skill):
        archive = self.root / "full.zip"
        core.export_data(self.store, archive)
        with zipfile.ZipFile(archive) as z:
            entries = {name: z.read(name) for name in z.namelist()}
        manifest = json.loads(entries["manifest.json"])
        manifest.update(source_version=version, source_skill=skill)
        entries["manifest.json"] = core.encoded(manifest)
        changed = self.root / "changed.zip"
        with zipfile.ZipFile(changed, "w") as z:
            for name, raw in entries.items():
                z.writestr(name, raw)
        return changed

    def test_120_archive_remains_importable(self):
        self.feedback()
        archive = self.archive_version("1.2.0-harness", "prompt-assistant-online-v1-2-0-harness")
        dest = core.Store(self.root / "dest")
        core.import_data(dest, archive)
        self.assertEqual(dest.load()["user_preferences"], self.store.load()["user_preferences"])

    def test_future_source_version_rejected(self):
        archive = self.archive_version("1.2.99-harness", core.SKILL)
        with self.assertRaises(core.HarnessError):
            core.load_archive(archive)

    def test_121_archive_remains_importable_in_122(self):
        self.feedback()
        archive = self.archive_version("1.2.1-harness", "prompt-assistant-online-v1-2-1-harness")
        dest = core.Store(self.root / "dest")
        core.import_data(dest, archive)
        self.assertEqual(dest.load()["user_preferences"], self.store.load()["user_preferences"])

    def test_mismatched_source_identity_rejected(self):
        archive = self.archive_version("1.2.0-harness", core.SKILL)
        with self.assertRaises(core.HarnessError):
            core.load_archive(archive)


if __name__ == "__main__":
    unittest.main()
