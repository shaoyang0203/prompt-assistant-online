"""Package integrity only; these tests do not score creative behavior."""
import shutil
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from harness_core import PACKAGE
from validate_harness import validate_package


class DesignIntegrityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "skill"
        shutil.copytree(PACKAGE, self.root)

    def test_current_revision_is_valid(self):
        self.assertTrue(validate_package(self.root)["valid"])

    def test_design_contract_change_is_detected(self):
        path = self.root / "references/design-contract.md"
        path.write_text("Translate user text directly.", encoding="utf-8")
        result = validate_package(self.root)
        self.assertFalse(result["valid"])
        self.assertTrue(any("design-contract.md" in error for error in result["errors"]))

    def test_missing_contract_is_reported(self):
        (self.root / "references/design-contract.md").unlink()
        self.assertFalse(validate_package(self.root)["valid"])

    def test_visual_knowledge_is_still_protected(self):
        path = self.root / "references/视觉设计系统/05-光线色彩与材质.md"
        path.write_text("Removed.", encoding="utf-8")
        result = validate_package(self.root)
        self.assertFalse(result["valid"])
        self.assertTrue(any("受保护" in error for error in result["errors"]))

    def test_consolidation_keeps_original_knowledge_protected(self):
        name = "references/视觉设计系统/06-审美与视觉语言.md"
        path = self.root / name
        path.write_bytes(path.read_bytes().replace("克制暖金宫廷".encode(), "已改变的宫廷".encode(), 1))
        manifest = self.root / "harness/design-protocol-integrity.json"
        revision = json.loads(manifest.read_text(encoding="utf-8"))
        revision["files"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(revision, ensure_ascii=False), encoding="utf-8")
        result = validate_package(self.root)
        self.assertFalse(result["valid"])
        self.assertTrue(any("受保护" in error for error in result["errors"]))

    def test_missing_consolidated_entry_is_detected(self):
        name = "references/视觉设计系统/06-审美与视觉语言.md"
        revision = json.loads((self.root / "harness/design-protocol-integrity.json").read_text(encoding="utf-8"))
        path = self.root / name
        path.write_bytes(path.read_bytes().replace(revision["knowledge_additions"][name].encode(), b"", 1))
        result = validate_package(self.root)
        self.assertFalse(result["valid"])
        self.assertTrue(any("新增条目无法唯一定位" in error for error in result["errors"]))
