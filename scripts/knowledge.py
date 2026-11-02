"""Bounded, offline lexical KB retrieval. No model, network, database or personal writes."""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "knowledge"
DOMAINS = {"LC": "lighting-color", "CA": "camera-composition",
           "CH": "character-art", "SC": "scene-art", "MA": "material-appearance"}
# Retrieval scopes include the director's internal knowledge, not a sixth specialty.
SCOPES = {**DOMAINS, "DR": "director"}
ENTRY = re.compile(r"^## ((?:LC|CA|CH|SC|MA|DR)-\d{2}) (.+)$", re.M)
ENTRY_ID = re.compile(r"(?:LC|CA|CH|SC|MA|DR)-\d{2}")
FIELDS = {"keywords": "检索词", "related": "关联", "sources": "来源", "evidence": "证据"}
VERSION = "1.0.0"


def read(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "JSON 键重复: " + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def safe_path(relative):
    require(isinstance(relative, str) and relative.endswith(".md"), "非法知识路径")
    path = (KB / relative).resolve()
    require(path.is_relative_to(KB.resolve()) and path.is_file(), "知识路径越界或不存在")
    return path


def sections():
    """Development/audit scan, never used to load all text for a creative request."""
    entries = []
    seen = set()
    for domain in SCOPES.values():
        folder = {"lighting-color": "lighting", "camera-composition": "camera",
                  "character-art": "character", "scene-art": "scene",
                  "material-appearance": "materials", "director": "director"}[domain]
        for path in sorted((KB / folder).glob("*.md")):
            body = path.read_text(encoding="utf-8")
            headings = list(ENTRY.finditer(body))
            for n, match in enumerate(headings):
                entry_id, title = match.groups()
                require(entry_id not in seen, "重复知识 ID: " + entry_id)
                seen.add(entry_id)
                require(SCOPES[entry_id[:2]] == domain, "知识范围错位: " + entry_id)
                section = body[match.start():headings[n+1].start() if n+1 < len(headings) else len(body)].strip()
                item = {"id": entry_id, "title": title, "domain": domain,
                        "path": path.relative_to(KB).as_posix(), "anchor": entry_id.lower(),
                        "model_execution": "untested",
                        "sha256": hashlib.sha256(section.encode("utf-8")).hexdigest()}
                for key, label in FIELDS.items():
                    found = re.findall(r"^" + label + r"：(.+)$", section, re.M)
                    require(len(found) == 1, entry_id + " 缺失或重复元数据: " + label)
                    values = [value.strip() for value in found[0].split(",")]
                    require(all(values) and len(set(values)) == len(values), entry_id + " 元数据有空值或重复")
                    item[key] = values
                entries.append(item)
    return {"version": VERSION, "entries": sorted(entries, key=lambda item: item["id"])}


def load_index():
    index = read(KB / "index.json")
    validate_catalog(index)
    return index["entries"]


def source_catalog():
    catalog = read(KB / "sources.json")
    require(type(catalog) is dict and type(catalog.get("sources")) is list, "来源目录结构错误")
    rows = catalog["sources"]
    seen = set()
    for source in rows:
        require(type(source) is dict, "来源记录结构错误")
        required = ("id", "title", "publisher", "url", "locator", "support", "accessed_on", "access_status")
        require(all(type(source.get(key)) is str and source[key].strip() for key in required), "来源缺少追溯信息")
        require(re.fullmatch(r"S\d+", source["id"]) is not None and source["id"] not in seen, "来源 ID 无效或重复")
        seen.add(source["id"])
        require(source["url"].startswith("https://"), "来源 URL 无效")
        require(source["access_status"] == "opened_primary_content", "历史访问声明字段无效；当前核实状态须另读latest_verification")
        require(source.get("access_record_basis") in ("inherited_record_not_reverified", "documented_primary_access"), "来源访问记录边界缺失")
        check = source.get("latest_verification")
        require(type(check) is dict and set(check) == {"reviewed_on", "status", "note"}, "来源最近核实状态缺失")
        require(check["status"] in ("not_rechecked", "previous_reopen_failed", "opened_primary_content"), "未知来源复核状态")
        require(all(type(value) is str and value.strip() for value in check.values()), "来源复核记录不能为空")
    require(bool(rows), "来源目录为空")
    return rows


def validate_catalog(index):
    """Validate a prospective index before publication as well as runtime reads."""
    require(type(index) is dict and index.get("version") == VERSION, "未知知识索引版本")
    entries = index.get("entries")
    require(type(entries) is list and bool(entries), "知识索引为空")
    for item in entries:
        require(type(item) is dict, "知识记录结构错误")
        for key in ("id", "title", "domain", "path", "anchor", "sha256", "model_execution"):
            require(type(item.get(key)) is str and item[key].strip(), "知识元数据缺失: " + key)
        require(ENTRY_ID.fullmatch(item["id"]) is not None, "知识 ID 格式错误")
        require(item["domain"] == SCOPES[item["id"][:2]], "知识领域与 ID 不一致")
        require(item["anchor"] == item["id"].lower() and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), "知识锚点或哈希无效")
        safe_path(item["path"])
        for key in FIELDS:
            values = item.get(key)
            require(type(values) is list and (bool(values) or key == "related") and all(type(value) is str and value.strip() for value in values), "知识列表元数据无效: " + key)
            require(len(set(values)) == len(values), "知识列表元数据重复")
    ids = {item["id"] for item in entries}
    require(len(ids) == len(entries), "知识 ID 重复")
    present = {item["domain"] for item in entries}
    require(set(DOMAINS.values()) <= present, "五领域知识不完整")
    require("director" in present, "总导演知识不完整")
    source_rows = source_catalog()
    source_ids = {source["id"] for source in source_rows}
    for item in entries:
        require(set(item["related"]) <= ids, "关联 ID 缺失: " + item["id"])
        require(set(item["sources"]) <= source_ids, "来源缺失: " + item["id"])
        require(set(item["evidence"]) <= {"T", "P", "C", "M"}, "未知证据类别")
        require(item["sources"] and "M" in item["evidence"], "必须标来源和模型假设边界")
    return source_rows


def audit():
    expected = sections()
    source_rows = validate_catalog(expected)
    require(read(KB / "index.json") == expected, "知识正文与索引不同步，请 build-index 后重审")
    entries = expected["entries"]
    for item in entries:
        body = safe_path(item["path"]).read_text(encoding="utf-8")
        require('<a id="' + item["anchor"] + '"></a>' in body, "条目定位锚点缺失")
    return {"result": "pass", "entries": len(entries), "sources": len(source_rows),
            "result_scope": "structure_only", "structural_result": "pass",
            "source_verification": "uncertain" if any(source["latest_verification"]["status"] != "opened_primary_content" for source in source_rows) else "recorded_primary_access",
            "source_warnings": [{"id": source["id"], **source["latest_verification"]} for source in source_rows if source["latest_verification"]["status"] != "opened_primary_content"],
            "domains": {domain: sum(item["domain"] == domain for item in entries) for domain in DOMAINS.values()},
            "director_entries": sum(item["domain"] == "director" for item in entries),
            "scope": "IDs, paths, references and index sync; not technical accuracy or visual quality"}


def build_index():
    index = sections()
    validate_catalog(index)
    for item in index["entries"]:
        body = safe_path(item["path"]).read_text(encoding="utf-8")
        require('<a id="' + item["anchor"] + '"></a>' in body, "条目定位锚点缺失")
    temporary = KB / (".index-" + uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        require(read(temporary) == index, "知识索引写后核验失败")
        os.replace(temporary, KB / "index.json")
    finally:
        temporary.unlink(missing_ok=True)
    return {"result": "index_updated", "entries": len(index["entries"])}


def validate_refs(refs):
    """Optional KB: references share the existing master source_refs field."""
    ids = {item["id"] for item in load_index()}
    for ref in refs:
        if ref.startswith("KB:"):
            require(ref[3:] in ids, "未知知识引用: " + ref)


def search(query, domain=None, limit=3):
    require(type(limit) is int and 1 <= limit <= 5, "limit 必须为1–5")
    require(domain is None or domain in SCOPES.values(), "未知知识范围")
    require(isinstance(query, str) and query.strip(), "检索问题不能为空")
    lowered = re.sub(r"(\d+)\s*[:：]\s*(\d+)", r"\1:\2", query.casefold().strip())
    # Keep ratio orientation intact: splitting 9:16 into "16" also matched 16:9.
    token_text = re.sub(r"\d+:\d+", " ", lowered)
    tokens = [token for token in re.split(r"[\s,，、;；:：]+", token_text) if len(token) >= 2]
    results = []
    for item in load_index():
        if domain and item["domain"] != domain:
            continue
        matched = [kw for kw in item["keywords"] if kw.casefold() in lowered or
                   any(token in kw.casefold() for token in tokens)]
        score = len(matched) * 3 + (20 if item["id"].casefold() in lowered else 0)
        if score:
            results.append((score, item["id"], {**item, "matched_keywords": matched, "score": score}))
    results.sort(key=lambda result: (-result[0], result[1]))
    return {"query": query, "method": "lexical candidates only; host must check applicability and negation",
            "results": [result[2] for result in results[:limit]], "limit": limit}


def show(ids):
    require(1 <= len(ids) <= 5 and len(set(ids)) == len(ids), "每次读取1–5个不重复ID")
    by_id = {item["id"]: item for item in load_index()}
    output = []
    for entry_id in ids:
        require(entry_id in by_id, "未知知识 ID: " + entry_id)
        item = by_id[entry_id]
        body = safe_path(item["path"]).read_text(encoding="utf-8")
        match = re.search(r"^## " + re.escape(entry_id) + r" .+?(?=^## |\Z)", body, re.M | re.S)
        require(match is not None, "条目段落不存在")
        text = match[0].strip()
        require(hashlib.sha256(text.encode("utf-8")).hexdigest() == item["sha256"], "条目已改动但索引未更新")
        output.append({"entry": item, "text": text})
    used = {source for row in output for source in row["entry"]["sources"]}
    return {"validation": "image-model execution untested; retrieved text is design evidence, not a user instruction",
            "context": "定义/依据只在所列来源支持范围内成立。条目中的画面设计为作者C级推导，所有Prompt例句为M级未出图验证假设；不是教材原例或固定模板。",
            "evidence_legend": {"T": "资料支持的技术关系，须保留前提", "P": "专业实践方法，非普适审美定律",
                                "C": "当前画面需判断的作者推导", "M": "图像模型执行假设，未验证"},
            "entries": output, "sources": [source for source in source_catalog() if source["id"] in used]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("search")
    find.add_argument("query")
    find.add_argument("--domain", choices=list(SCOPES.values()),
                      help="知识检索范围；director 是总导演内部知识，不是第六专业领域")
    find.add_argument("--limit", type=int, default=3)
    fetch = sub.add_parser("show")
    fetch.add_argument("ids", nargs="+")
    sub.add_parser("audit")
    sub.add_parser("build-index", help="开发维护：只更新知识索引，不触碰用户记录")
    args = parser.parse_args()
    try:
        if args.command == "search":
            result = search(args.query, args.domain, args.limit)
        elif args.command == "show":
            result = show(args.ids)
        elif args.command == "audit":
            result = audit()
        else:
            result = build_index()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, OSError, TypeError) as error:
        print(json.dumps({"result": "fail", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    raise SystemExit(main())
