"""偏好模板、存档与推断的确定性检查。只用标准库，不调用模型。

运行：<python> -B -X utf8 tests/test_prefs.py
受限沙箱里若临时目录不可写，先设 PA_TEST_TMP 指向一个可写的普通目录。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "scripts" / "prefs.py"


def run(data_dir, *args, expect=0):
    command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT), "--data-dir", str(data_dir), *args]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == expect, (args, result.returncode, result.stderr)
    if expect == 0:
        return json.loads(result.stdout)
    return json.loads(result.stderr)


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return str(path)


def main():
    base = os.environ.get("PA_TEST_TMP") or None
    if base:
        # 受限沙箱里 mkdtemp 会建出 0o700 目录，后续写入被拒；这里用普通权限自建。
        base = Path(base)
        base.mkdir(parents=True, exist_ok=True)
        folder = base / ("pa-prefs-" + str(os.getpid()))
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
    else:
        folder = Path(tempfile.mkdtemp(prefix="pa-prefs-"))
    try:
        data = folder / "data"
        run(data, "init")

        sexy = write(folder / "t1.json", {
            "name": "性感", "dimension": "subject",
            "attributes": ["胸部体积明显", "腰线内收", "髋部宽", "黑色丝袜"],
            "apply_mode": "default_fill", "default_on": True})
        first = run(data, "template", "add", "--input", sexy)
        assert first["saved"] and first["template"]["id"] == "T0001"

        # 评价词不能作为属性
        bad = write(folder / "t2.json", {
            "name": "氛围", "dimension": "lighting",
            "attributes": ["电影感侧光"], "apply_mode": "prefer"})
        error = run(data, "template", "add", "--input", bad, expect=1)
        assert "评价词" in error["error"], error

        # 同维度替换
        thin = write(folder / "t3.json", {
            "name": "清瘦", "dimension": "subject",
            "attributes": ["肩窄", "腰细", "四肢修长"], "apply_mode": "default_fill"})
        run(data, "template", "add", "--input", thin)
        switched = run(data, "template", "on", "--id", "T0002")
        assert switched["displaced"] == ["T0001"], switched

        # 存档必须带母版与提示词原文
        master = json.loads((PACKAGE / "tests/fixtures/master.json").read_text(encoding="utf-8"))
        archive = write(folder / "a1.json", {
            "master": master, "prompt": "成品原文。", "rating": "喜欢", "target": "image"})
        saved = run(data, "archive", "add", "--input", archive)
        assert saved["archive"]["id"] == "A0001"

        # 推断一律 pending，且不能直接设为默认
        infer = write(folder / "i1.json", {
            "request": "总结我的偏好", "basis": ["A0001"],
            "candidates": [{"name": "窗侧柔光", "dimension": "lighting",
                            "attributes": ["左侧大面柔光"], "apply_mode": "prefer",
                            "scope": {"scene": "室内", "model": "*"}}]})
        pending = run(data, "infer", "--input", infer)
        assert pending["templates"][0]["status"] == "pending", pending

        # 记录开关关闭后拒绝写入
        run(data, "set", "--key", "record", "--value", "off")
        rejected = run(data, "template", "add", "--input", thin, expect=1)
        assert "记录开关已关闭" in rejected["error"], rejected
        run(data, "set", "--key", "record", "--value", "on")

        # 数据目录不得落在技能源码内
        inside = run(PACKAGE, "status", expect=1)
        assert "源码目录" in inside["error"], inside

        # 备份在写入后存在
        assert (data / "preferences.json.bak").exists()
        status = run(data, "status")
        assert status["counts"]["archive"] == 1, status
        assert status["defaults"] == {"subject": "T0002"}, status
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    print(json.dumps({"result": "pass", "cases": 8,
                      "scope": "结构、开关、作用域与源码隔离；不证明审美效果"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())
