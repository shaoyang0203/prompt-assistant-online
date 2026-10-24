"""Build a verified installable ZIP with one named skill directory."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from harness_core import PACKAGE, SKILL, atomic, encoded
from validate_harness import validate_package


def build(output):
    result = validate_package()
    if not result["valid"]:
        raise ValueError(result["errors"])
    report = json.loads((PACKAGE / "harness/test-results.json").read_text(encoding="utf-8"))
    if report["failures"] or report["errors"] or report["skipped"] or report["tests"] < 60:
        raise ValueError("自动化测试报告未通过")
    for name, expected in report["tested_files"].items():
        if hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() != expected:
            raise ValueError("代码在测试后发生变化，需重新测试: " + name)
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(PACKAGE):
        raise ValueError("输出需为 Skill 外的全新 ZIP 路径")
    if output.is_relative_to((PACKAGE.parent / "V1.2.0-VIP").resolve()):
        raise ValueError("发行包不得写入 VIP 基线")
    files = {p.relative_to(PACKAGE).as_posix(): p.read_bytes() for p in PACKAGE.rglob("*") if p.is_file()}
    manifest = {"skill": SKILL, "version": "1.2.0-harness", "files":
                {n: hashlib.sha256(v).hexdigest() for n, v in sorted(files.items())}}
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "release.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, raw in files.items():
                z.writestr(SKILL + "/" + name, raw)
            z.writestr(SKILL + "/RELEASE-MANIFEST.json", encoded(manifest))
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:
                raise ValueError("ZIP CRC 失败")
            for name, expected in manifest["files"].items():
                if hashlib.sha256(z.read(SKILL + "/" + name)).hexdigest() != expected:
                    raise ValueError("ZIP 文件完整性失败: " + name)
        atomic(output, path.read_bytes())
    result = {"path": str(output), "files": len(files) + 1,
              "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "zip_verified": True}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
