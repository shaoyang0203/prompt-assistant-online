"""Standard-library validation of the JSON Schema subset used by V1.5.2.
Not a general Draft 2020-12 validator. No remote schema resolution.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZONES = {
    "intent_constraints": "创作意图与用户约束",
    "creative_direction_moment": "创意方向与叙事瞬间",
    "visual_subject_hierarchy": "视觉主体与层级",
    "character_art": "人物美术",
    "scene_art": "场景美术",
    "action_spatial_relations": "动作与空间关系",
    "camera_composition": "摄影与构图",
    "lighting_color": "光影与色彩",
    "material_visual_expression": "材质与视觉表现",
}
COMPILED_KINDS = {"visual_fact", "medium", "aspect_ratio", "image_text"}
VERSION = "1.5.2"

class ContractError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise ContractError(message)

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()

def read_json(path):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, "JSON 包含重复键: " + k)
            result[k] = v
        return result
    return json.loads(Path(path).read_bytes().decode("utf-8-sig"),
                      object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ContractError("非法数值: " + s)))

def schema_errors(value, spec, root=None, path="$"):
    root = spec if root is None else root
    errors = []
    if "$ref" in spec:
        ref = spec["$ref"]
        require(ref.startswith("#/"), "仅支持本地 Schema 引用")
        target = root
        for part in ref[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        errors += schema_errors(value, target, root, path)
    types = {
        "object": lambda x: type(x) is dict,
        "array": lambda x: type(x) is list,
        "string": lambda x: type(x) is str,
        "integer": lambda x: type(x) is int,
        "number": lambda x: type(x) in (int, float),
        "boolean": lambda x: type(x) is bool,
        "null": lambda x: x is None,
    }
    if "type" in spec:
        names = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
        if not any(types[t](value) for t in names):
            return errors + [path + ": 类型错误"]
    if "const" in spec and encode(value) != encode(spec["const"]):
        errors.append(path + ": 常量不匹配")
    if "enum" in spec and not any(encode(value) == encode(x) for x in spec["enum"]):
        errors.append(path + ": 枚举值错误")
    if type(value) is str:
        if len(value) < spec.get("minLength", 0) or not value.strip():
            errors.append(path + ": 文本为空")
        if "pattern" in spec and re.search(spec["pattern"], value) is None:
            errors.append(path + ": 格式错误")
    if type(value) in (int, float):
        if "minimum" in spec and value < spec["minimum"]:
            errors.append(path + ": 数值过小")
    if type(value) is dict:
        for key in spec.get("required", []):
            if key not in value:
                errors.append(path + ": 缺少 " + key)
        if len(value) < spec.get("minProperties", 0):
            errors.append(path + ": 对象为空")
        props = spec.get("properties", {})
        for key, item in value.items():
            if "propertyNames" in spec:
                errors += schema_errors(key, spec["propertyNames"], root, path + ".<key>")
            if key in props:
                errors += schema_errors(item, props[key], root, path + "." + key)
            elif spec.get("additionalProperties") is False:
                errors.append(path + ": 未知字段 " + key)
            elif type(spec.get("additionalProperties")) is dict:
                errors += schema_errors(item, spec["additionalProperties"], root, path + "." + key)
    if type(value) is list:
        if len(value) < spec.get("minItems", 0):
            errors.append(path + ": 数组过短")
        if spec.get("uniqueItems") and len({encode(x) for x in value}) != len(value):
            errors.append(path + ": 数组重复")
        for n, item in enumerate(value):
            if "items" in spec:
                errors += schema_errors(item, spec["items"], root, path + "[" + str(n) + "]")
    for sub in spec.get("allOf", []):
        errors += schema_errors(value, sub, root, path)
    if "oneOf" in spec:
        if sum(not schema_errors(value, sub, root, path) for sub in spec["oneOf"]) != 1:
            errors.append(path + ": oneOf 不匹配")
    if "if" in spec:
        branch = "then" if not schema_errors(value, spec["if"], root, path) else "else"
        if branch in spec:
            errors += schema_errors(value, spec[branch], root, path)
    return errors

def validate_master(master):
    spec = read_json(ROOT / "schemas" / "visual-master.schema.json")
    errors = schema_errors(master, spec)
    require(not errors, "Schema: " + "; ".join(errors[:12]))
    items = master["items"]
    refs = [x for zone in master["zones"].values() for x in zone]
    refs += [master["globals"]["medium"], master["globals"]["aspect_ratio"]]
    refs += master["globals"]["image_text"]
    require(set(refs) <= set(items), "母版包含悬空引用")
    require(set(refs) == set(items), "存在未展示的孤立设计项")
    require(items[master["globals"]["medium"]]["kind"] == "medium", "媒介引用类型错误")
    require(items[master["globals"]["aspect_ratio"]]["kind"] == "aspect_ratio", "比例引用类型错误")
    require(all(items[x]["kind"] == "image_text" for x in master["globals"]["image_text"]), "文字引用类型错误")
    for key, item in items.items():
        kb_refs = [ref for ref in item["source_refs"] if ref.startswith("KB:")]
        if kb_refs:
            from knowledge import validate_refs
            try:
                validate_refs(kb_refs)
            except (ValueError, KeyError, OSError, TypeError) as error:
                raise ContractError("知识引用无效: " + str(error)) from error
        require(item["confirmation_status"] != "rejected", "拒绝的设计不能进入当前有效母版: " + key)
        if item["design_source"] == "user_specified":
            require(item["confirmation_status"] == "confirmed", "用户指定项确认状态必须为 confirmed")
            if item["kind"] == "aspect_ratio":
                require(item["constraint_strength"] == "hard_constraint", "用户明确指定的画幅必须是硬性约束")
        deps = [d["item_id"] for d in item["depends_on"]]
        require(key not in deps and set(deps) <= set(items), "设计依赖无效: " + key)
        links = item.get("realized_by", [])
        require(key not in links and set(links) <= set(items), "要求落实引用无效")
        if item["kind"] == "constraint":
            require(bool(links), "约束缺少正向落实项: " + key)
            require(all(items[x]["kind"] in COMPILED_KINDS for x in links), "约束必须映射到可编译事实")
    return master

def impact(old, new, seeds):
    affected = set(seeds)
    changed = True
    while changed:
        changed = False
        for master in (old, new):
            for key, item in master["items"].items():
                refs = {d["item_id"] for d in item["depends_on"]} | set(item.get("realized_by", []))
                if refs & affected and key not in affected:
                    affected.add(key)
                    changed = True
    return sorted(affected)

