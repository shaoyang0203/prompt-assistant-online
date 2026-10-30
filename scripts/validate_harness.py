"""Validate package links, defaults, source preservation and executable syntax."""
import sys
sys.dont_write_bytecode = True
import ast
import hashlib
import json
from pathlib import Path
import re

from harness_core import PACKAGE, DEFAULT, validate_config, read_json


def validate_package(root=PACKAGE, source=None):
    root = Path(root)
    errors = []
    required = ("SKILL.md", "references/harness-help.md", "references/harness-protocol.md",
                "harness/README.md", "harness/config.json", "harness/source-baseline.json",
                "scripts/harness_core.py", "scripts/check_harness_environment.py",
                "scripts/export_harness.py", "scripts/import_harness.py", "tests/test_harness.py",
                "harness/schemas/user-preferences.schema.json", "harness/schemas/learned-overrides.schema.json",
                "harness/schemas/migration-manifest.schema.json")
    required += ("references/design-contract.md", "tests/design-cases.json",
                 "harness/design-protocol-integrity.json", "references/风格推荐库.md")
    for name in required:
        if not (root / name).is_file():
            errors.append("缺少文件: " + name)
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if target.startswith(("http:", "https:", "mailto:", "#")):
                continue
            if not (path.parent / target.split("#")[0]).resolve().exists():
                errors.append("引用不存在: " + str(path.relative_to(root)) + " -> " + target)
    for path in root.rglob("*.py"):
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            errors.append(str(exc))
    for path in root.rglob("*.json"):
        try:
            read_json(path)
        except ValueError as exc:
            errors.append(str(path) + ": " + str(exc))
    config = read_json(root / "harness/config.json")
    validate_config(config)
    if config != DEFAULT:
        errors.append("发行默认配置必须保持关闭且无用户设置")
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    if not re.match(r"---\nname: [a-z0-9-]{1,64}\ndescription: [^\n]+\n---", skill):
        errors.append("Skill frontmatter 无效")
    baseline = read_json(root / "harness/source-baseline.json")
    revision_path = root / "harness/design-protocol-integrity.json"
    revision = read_json(revision_path) if revision_path.is_file() else {}
    revision_files = {"SKILL.md", "references/Adapter与交付.md",
                      "references/视觉设计系统/06-审美与视觉语言.md",
                      "references/视觉设计系统/07-约束与质量检查.md",
                      "references/design-contract.md", "tests/design-cases.json",
                      "references/Qwen-Image-2.1-T2I.md", "references/VIP偏好学习.md",
                      "references/harness-help.md", "references/harness-protocol.md"}
    revision_files |= {"references/视觉设计系统/04-构图与空间.md", "references/风格推荐库.md"}
    if set(revision.get("files", {})) != revision_files:
        errors.append("设计协议修订清单不完整")
    for name in revision_files:
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != revision.get("files", {}).get(name):
            errors.append("设计协议文件与本次修订清单不符: " + name)

    def before_upgrade(text, name):
        patch = revision.get("v14_edits", {}).get(name, {})
        for edit in reversed(patch.get("edits", [])):
            if not edit["new"] or text.count(edit["new"]) != 1:
                errors.append("V1.4 修订无法唯一还原: " + name)
                return text
            text = text.replace(edit["new"], edit["old"], 1)
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != patch.get("base_sha256"):
            errors.append("V1.4 修订的 V1.3.0 来源正文不符: " + name)
        return text

    upgrade_files = revision_files - {"references/风格推荐库.md"}
    if set(revision.get("v14_edits", {})) != upgrade_files:
        errors.append("V1.4 修订清单不完整")
    prior13 = {name: before_upgrade((root / name).read_text(encoding="utf-8"), name)
               for name in upgrade_files if (root / name).is_file()}

    def before_release(text, name):
        patch = revision.get("release_edits", {}).get(name, {})
        for edit in reversed(patch.get("edits", [])):
            if not edit["new"] or text.count(edit["new"]) != 1:
                errors.append("发行修订无法唯一还原: " + name)
                return text
            text = text.replace(edit["new"], edit["old"], 1)
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != patch.get("base_sha256"):
            errors.append("发行修订的 1.22 来源正文不符: " + name)
        return text

    release_files = {"SKILL.md", "references/Adapter与交付.md",
                     "references/视觉设计系统/07-约束与质量检查.md",
                     "references/Qwen-Image-2.1-T2I.md", "references/VIP偏好学习.md",
                     "references/harness-help.md", "references/harness-protocol.md"}
    if set(revision.get("release_edits", {})) != release_files:
        errors.append("发行文档修订清单不完整")
    prior = {name: before_release(prior13[name], name)
             for name in release_files if (root / name).is_file()}

    def design_revision(text, name):
        # Apply the recorded, reviewable edits to the previously preserved VIP body.
        patch = revision.get("legacy_edits", {}).get(name, {})
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != patch.get("base_sha256"):
            errors.append("设计修订的来源正文不符: " + name)
            return text
        for edit in patch.get("edits", []):
            if not edit["old"] or text.count(edit["old"]) != 1:
                errors.append("设计修订无法唯一定位: " + name)
                return text
            text = text.replace(edit["old"], edit["new"], 1)
        return text
    preserved = [n for n in baseline["files"] if n.startswith("references/视觉设计系统/") and not n.endswith("07-约束与质量检查.md")]
    additions = revision.get("knowledge_additions", {})
    if set(additions) != {"references/视觉设计系统/06-审美与视觉语言.md"}:
        errors.append("视觉知识新增条目清单不完整")
    # Newlines are normalized by the integration; compare original bytes for untouched resources.
    for name in preserved:
        raw = (root / name).read_bytes()
        if name in prior13:
            prior_text = prior13[name]
            if revision.get("v14_edits", {}).get(name, {}).get("base_newlines") == "CRLF":
                prior_text = prior_text.replace("\n", "\r\n")
            raw = prior_text.encode("utf-8")
        if name in additions:
            insertion = additions[name].encode("utf-8")
            if not insertion or raw.count(insertion) != 1:
                errors.append("视觉知识新增条目无法唯一定位: " + name)
            else:
                raw = raw.replace(insertion, b"", 1)
        if hashlib.sha256(raw).hexdigest() != baseline["files"][name]:
            errors.append("受保护的视觉/Adapter 文件发生变化: " + name)
    if source is not None:
        source = Path(source)
        actual = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in source.rglob("*") if p.is_file()}
        if actual != baseline["files"]:
            errors.append("VIP 原始文件与基线清单不一致")
        original = (source / "SKILL.md").read_text(encoding="utf-8")
        # All sections from product positioning onward are retained, except explicitly changed metadata.
        original_body = original[original.index("## 产品定位"):]
        expected = original_body.replace("V1.2.0 VIP", "V1.2 Harness")
        expected = expected.replace("- `用户偏好.md`：独立的用户数据文件，保存偏好、案例、原始反馈与待验证推测。",
                                    "- `用户偏好.md`：保留的空白 VIP 模板，运行时不写入；个人数据位于外部 Harness 目录。")
        expected = expected.replace("非首次回复且用户明确要求生成时，只交付代码块，不重复开场；",
                                    "非首次回复且用户明确要求生成时，先显示实际状态，再交付代码块，不重复开场；")
        expected = design_revision(expected, "SKILL.md").replace("正在调用提示词助手 V1.2 Harness", "正在调用提示词助手 V1.22 Harness")
        if prior["SKILL.md"][prior["SKILL.md"].index("## 产品定位"):] != expected:
            errors.append("核心正文超出已记录的 Harness 与设计修订")
        adapter = (source / "references/Adapter与交付.md").read_text(encoding="utf-8")
        expected_adapter = adapter.replace("正在调用提示词助手 V1.2.0 VIP", "正在调用提示词助手 V1.2 Harness")
        expected_adapter = expected_adapter.replace("只输出代码块，不重复开场", "先输出实时状态标记，再输出代码块，不重复开场")
        expected_adapter = expected_adapter.replace("# Adapter 与交付", "# Adapter 与交付\n\nHarness 元信息遵循 SKILL.md：每轮先显示实际状态，首次另有开场与启用说明，均位于代码块外。以下交付条款只规定 Prompt 本身。", 1)
        expected_adapter = design_revision(expected_adapter, "references/Adapter与交付.md").replace("正在调用提示词助手 V1.2 Harness", "正在调用提示词助手 V1.22 Harness")
        if prior["references/Adapter与交付.md"] != expected_adapter:
            errors.append("Adapter 发生超出已记录的设计接入改动")
    forbidden = {"CURRENT", "user_preferences.json", "learned_overrides.json", "candidates.json",
                 "evolution_log.jsonl", ".writer.lock", "health.json"}
    for path in root.rglob("*"):
        if path.name in forbidden or "generations" in path.relative_to(root).parts:
            errors.append("发行目录含运行时个人数据: " + str(path.relative_to(root)))
        if path.name == "__pycache__" or path.suffix in (".pyc", ".pyo") or path.name.startswith((".probe-", "backup-")):
            errors.append("发行目录含 Python 缓存")
    return {"valid": not errors, "errors": errors, "baseline_files": len(baseline["files"]),
            "protected_files": len(preserved), "source_verified": source is not None}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source")
    args = parser.parse_args()
    result = validate_package(source=args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(not result["valid"])
