"""Run isolated synthetic tests and write an auditable local report."""
import sys
sys.dont_write_bytecode = True
import io
import hashlib
import json
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
stream = io.StringIO()
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
text = stream.getvalue()
print(text)
report = {"time": datetime.now(timezone.utc).isoformat(), "tests": result.testsRun,
          "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
          "python": sys.version, "platform": sys.platform,
          "scope": "Windows local; synthetic text evidence only; permission/read/cleanup faults injected with mocks",
          "output": text}
report["tested_files"] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for folder in ("scripts", "tests") for p in (ROOT / folder).rglob("*.py")}
(ROOT / "harness" / "test-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
raise SystemExit(not result.wasSuccessful())
