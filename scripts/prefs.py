#!/usr/bin/env python3
"""V1.5.3 偏好模板、存档与推断。只写外部数据目录，不写源码，不调用模型。

模板取自母版的设计方向，不取自提示词。提示词是母版的译本，永远在下游。
"""
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from contracts import validate_master

PACKAGE = Path(__file__).resolve().parents[1]
VERSION = "1.5.3"
FORMAT = 1
DIMENSIONS = ("subject", "lighting", "palette", "camera", "material")
APPLY_MODES = ("default_fill", "prefer", "avoid")
SOURCES = ("user_specified", "master_extracted", "inferred")
STATUSES = ("active", "pending", "disabled")
RATINGS = ("特别喜欢", "喜欢", "一般", "厌恶")
SETTINGS = ("record", "apply", "remind")

# 模板名可以叫“性感”；属性必须是可见事实。以下评价词不允许出现在属性里。
EVALUATIVE = ("性感", "高级感", "电影感", "氛围感", "精致", "唯美", "好看", "漂亮",
              "大片感", "故事感", "情绪感")

TEMPLATE_REQUIRED = {"id", "name", "dimension", "attributes", "apply_mode", "scope",
                     "default_on", "status", "source"}
TEMPLATE_KEYS = TEMPLATE_REQUIRED | {"source_items", "evidence", "note", "created", "updated"}


class PrefsError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PrefsError(message)


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "JSON 包含重复键: " + key)
            result[key] = value
        return result

    return json.loads(Path(path).read_bytes().decode("utf-8-sig"),
                      object_pairs_hook=unique,
                      parse_constant=lambda token: (_ for _ in ()).throw(
                          PrefsError("非法数值: " + token)))


def blank():
    return {"format": FORMAT, "version": VERSION,
            "settings": {"record": True, "apply": True, "remind": True},
            "templates": [], "archive": [], "log": []}


# ---------- 校验 ----------

def validate_template(template):
    require(type(template) is dict, "模板必须是对象")
    missing = TEMPLATE_REQUIRED - set(template)
    require(not missing, "模板缺少字段: " + ",".join(sorted(missing)))
    unknown = set(template) - TEMPLATE_KEYS - {"confirmed_by"}
    require(not unknown, "模板包含未知字段: " + ",".join(sorted(unknown)))
    require(re.fullmatch(r"T\d{4}", str(template["id"])) is not None, "模板 ID 必须形如 T0001")
    require(type(template["name"]) is str and template["name"].strip(), "模板名不能为空")
    require(template["dimension"] in DIMENSIONS,
            "未知维度；只允许 " + "/".join(DIMENSIONS))
    attributes = template["attributes"]
    require(type(attributes) is list and bool(attributes) and
            all(type(a) is str and a.strip() for a in attributes),
            "模板属性必须是非空字符串数组")
    require(len(set(attributes)) == len(attributes), "模板属性重复")
    for attribute in attributes:
        hit = [word for word in EVALUATIVE if word in attribute]
        require(not hit, "模板属性必须是可见事实，不能写评价词 " + "/".join(hit) +
                "（可以改进模板名，但属性要写看得见的东西）：" + attribute)
    require(template["apply_mode"] in APPLY_MODES,
            "未知作用模式；只允许 " + "/".join(APPLY_MODES))
    scope = template["scope"]
    require(type(scope) is dict and set(scope) == {"scene", "model"},
            "作用域必须且只能有 scene 与 model 两个键")
    require(all(type(value) is str and value.strip() for value in scope.values()),
            "作用域取值不能为空；不限写 *")
    require(type(template["default_on"]) is bool, "default_on 必须是布尔值")
    require(template["status"] in STATUSES, "未知状态")
    require(template["source"] in SOURCES, "未知来源")
    require(template["apply_mode"] != "avoid" or not template["default_on"],
            "avoid 模板始终生效，不设 default_on")
    if template["default_on"]:
        require(template["status"] == "active", "只有 active 模板能设为默认开启")
    if template["source"] == "inferred" and template["status"] == "active":
        require(bool(str(template.get("confirmed_by", "")).strip()),
                "推断得到的模板必须经用户确认后才能生效")
    items = template.get("source_items", [])
    require(type(items) is list, "source_items 必须是数组")
    for item in items:
        require(type(item) is dict and set(item) == {"facet", "value"} and
                all(type(value) is str and value.strip() for value in item.values()),
                "source_items 每项必须只含非空的 facet 与 value")
    if template["source"] == "master_extracted":
        require(bool(items), "从母版提取的模板必须记录 source_items")
    evidence = template.get("evidence", [])
    require(type(evidence) is list and
            all(type(x) is str and x.strip() for x in evidence), "evidence 必须是字符串数组")
    require(type(template.get("note", "")) is str, "note 必须是字符串")


def validate_archive(record):
    require(type(record) is dict, "存档必须是对象")
    require(set(record) == {"id", "master", "prompt", "rating", "target", "note", "time"},
            "存档字段必须为 id/master/prompt/rating/target/note/time")
    require(re.fullmatch(r"A\d{4}", str(record["id"])) is not None, "存档 ID 必须形如 A0001")
    require(type(record["master"]) is dict, "存档必须包含母版")
    validate_master(record["master"])
    require(type(record["prompt"]) is str and record["prompt"].strip(),
            "存档必须保存提示词原文；只记好评不保存原文等于没记")
    require(record["rating"] in RATINGS, "评价必须在四档内")
    require(record["target"] in ("image", "prompt"), "赞赏对象必须是 image 或 prompt")
    require(type(record["note"]) is str, "note 必须是字符串")
    require(type(record["time"]) is str and record["time"].strip(), "缺少时间")


def validate(data):
    require(type(data) is dict, "偏好库结构错误")
    require(set(data) == {"format", "version", "settings", "templates", "archive", "log"},
            "偏好库字段必须为 format/version/settings/templates/archive/log")
    require(data["format"] == FORMAT, "偏好库格式版本不支持: " + str(data["format"]))
    settings = data["settings"]
    require(type(settings) is dict and set(settings) == set(SETTINGS) and
            all(type(value) is bool for value in settings.values()), "设置字段错误")
    for key in ("templates", "archive", "log"):
        require(type(data[key]) is list, key + " 必须是数组")
    ids, names, defaults = set(), set(), {}
    for template in data["templates"]:
        validate_template(template)
        require(template["id"] not in ids, "模板 ID 重复: " + template["id"])
        ids.add(template["id"])
        name = (template["dimension"], template["name"])
        require(name not in names, "同维度模板名重复: " + template["name"])
        names.add(name)
        if template["default_on"]:
            require(template["dimension"] not in defaults,
                    "同维度只能有一个默认模板: " + template["dimension"])
            defaults[template["dimension"]] = template["id"]
    archive_ids = set()
    for record in data["archive"]:
        validate_archive(record)
        require(record["id"] not in archive_ids, "存档 ID 重复: " + record["id"])
        archive_ids.add(record["id"])
    for event in data["log"]:
        require(type(event) is dict and set(event) == {"time", "action", "target", "summary"},
                "日志记录字段错误")
        require(all(type(value) is str for value in event.values()), "日志记录必须是字符串")


def next_id(prefix, rows):
    numbers = [int(row["id"][1:]) for row in rows
               if re.fullmatch(prefix + r"\d{4}", str(row.get("id", "")))]
    return prefix + str(max(numbers, default=0) + 1).zfill(4)


def journal(data, action, target, summary):
    data["log"].append({"time": now(), "action": action, "target": target, "summary": summary})


# ---------- 存储 ----------

class Prefs:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        require(not (self.root == PACKAGE or self.root.is_relative_to(PACKAGE)),
                "偏好数据不得写入技能源码目录；请给出源码之外的目录")
        self.path = self.root / "preferences.json"

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ".prefs.lock"
        try:
            handle = path.open("x", encoding="utf-8")
        except FileExistsError as exc:
            raise PrefsError("偏好库正在写入或存在遗留锁；核实进程后手动处理，不自动抢锁") from exc
        try:
            with handle:
                handle.write(str(os.getpid()))
            yield
        finally:
            path.unlink()

    def load(self):
        if not self.path.exists():
            return blank()
        data = read_json(self.path)
        validate(data)
        return data

    def save(self, data):
        validate(data)
        self.root.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.root / "preferences.json.bak")
        temporary = self.root / (".preferences-" + uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                        indent=2).encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            require(read_json(temporary) == data, "写入后回读核验失败，未替换正式文件")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return {"saved": True, "path": str(self.path), "sha256": digest(data)[:12]}

    def change(self, action):
        with self.lock():
            data = self.load()
            original = copy.deepcopy(data)
            result = action(data)
            if data == original:
                return {**result, "saved": False, "note": "无变化，未写入"}
            return {**result, **self.save(data)}


# ---------- 查询 ----------

def scope_match(template, scene, model):
    scope = template["scope"]
    return (scope["scene"] in ("*", scene or "")
            and scope["model"] in ("*", model or ""))


def query_view(data, scene=None, model=None, dimension=None):
    active = [t for t in data["templates"] if t["status"] == "active"]
    if dimension:
        active = [t for t in active if t["dimension"] == dimension]
    scoped = [t for t in active if scope_match(t, scene, model)]
    return {
        "defaults": [t for t in scoped if t["apply_mode"] == "default_fill" and t["default_on"]],
        "prefer": [t for t in scoped if t["apply_mode"] == "prefer" and t["default_on"]],
        "optional": [t for t in scoped if t["apply_mode"] in ("default_fill", "prefer")
                     and not t["default_on"]],
        "avoid": [t for t in scoped if t["apply_mode"] == "avoid"],
        "pending": [t for t in data["templates"] if t["status"] == "pending"
                    and (not dimension or t["dimension"] == dimension) and scope_match(t, scene, model)],
    }


# ---------- 命令 ----------

def validate_input_types(payload):
    attributes = payload.get("attributes")
    require(type(attributes) is list and bool(attributes) and
            all(type(value) is str and value.strip() for value in attributes),
            "attributes 必须是非空字符串数组，不接受字符串或其他类型强转")
    require(type(payload.get("default_on", False)) is bool, "default_on 必须是布尔值")
    require(type(payload.get("source_items", [])) is list, "source_items 必须是数组")
    evidence = payload.get("evidence", [])
    require(type(evidence) is list and all(type(value) is str and value.strip() for value in evidence),
            "evidence 必须是字符串数组")


def command_add(prefs, payload):
    require(type(payload) is dict, "模板输入必须是对象")
    allowed = {"name", "dimension", "attributes", "apply_mode", "scope", "default_on",
               "source", "source_items", "evidence", "note"}
    unknown = set(payload) - allowed
    require(not unknown, "模板输入包含未知字段: " + ",".join(sorted(unknown)))
    for key in ("name", "dimension", "attributes", "apply_mode"):
        require(key in payload, "模板输入缺少 " + key)
    validate_input_types(payload)

    def action(data):
        require(data["settings"]["record"], "记录开关已关闭；先 `set --key record --value on`")
        template = {
            "id": next_id("T", data["templates"]),
            "name": payload["name"],
            "dimension": payload["dimension"],
            "attributes": copy.deepcopy(payload["attributes"]),
            "apply_mode": payload["apply_mode"],
            "scope": payload.get("scope", {"scene": "*", "model": "*"}),
            "default_on": payload.get("default_on", False),
            "status": "active",
            "source": payload.get("source", "user_specified"),
            "source_items": copy.deepcopy(payload.get("source_items", [])),
            "evidence": copy.deepcopy(payload.get("evidence", [])),
            "note": payload.get("note", ""),
            "created": now(),
            "updated": now(),
        }
        if template["source"] == "inferred":
            template["status"] = "pending"
            template["default_on"] = False
        displaced = []
        if template["default_on"]:
            for other in data["templates"]:
                if other["dimension"] == template["dimension"] and other["default_on"]:
                    other["default_on"] = False
                    displaced.append(other["id"])
        data["templates"].append(template)
        journal(data, "template.add", template["id"],
                template["name"] + "｜" + template["dimension"] + "｜" + template["apply_mode"])
        return {"template": template, "displaced": displaced}

    return prefs.change(action)


def find(data, template_id):
    template = next((t for t in data["templates"] if t["id"] == template_id), None)
    require(template is not None, "模板不存在: " + str(template_id))
    return template


def command_on(prefs, template_id):
    def action(data):
        template = find(data, template_id)
        require(template["apply_mode"] != "avoid", "avoid 模板始终生效，不需要开启")
        if template["status"] == "pending":
            template["status"] = "active"
            template["confirmed_by"] = "user"
        require(template["status"] == "active", "模板已停用；先恢复到 active 再开启")
        displaced = []
        for other in data["templates"]:
            if (other["id"] != template["id"] and other["dimension"] == template["dimension"]
                    and other["default_on"]):
                other["default_on"] = False
                displaced.append(other["id"])
        template["default_on"] = True
        template["updated"] = now()
        journal(data, "template.on", template["id"], template["name"] + " 设为默认开启")
        return {"template": template, "displaced": displaced,
                "note": "同维度旧的默认模板已自动关闭" if displaced else "同维度无其他默认模板"}

    return prefs.change(action)


def command_off(prefs, template_id):
    def action(data):
        template = find(data, template_id)
        template["default_on"] = False
        template["updated"] = now()
        journal(data, "template.off", template["id"], template["name"] + " 取消默认开启（仍可点名使用）")
        return {"template": template}

    return prefs.change(action)


def command_stop(prefs, template_id, reason):
    def action(data):
        template = find(data, template_id)
        template["status"] = "disabled"
        template["default_on"] = False
        template["updated"] = now()
        journal(data, "template.stop", template["id"],
                (reason or "用户停用") + "｜" + template["name"])
        return {"template": template}

    return prefs.change(action)


def command_resume(prefs, template_id):
    def action(data):
        template = find(data, template_id)
        require(template["status"] == "disabled", "resume 仅恢复已停用模板；pending 推断须用 template on 经用户明确确认")
        require(template["source"] != "inferred" or bool(template.get("confirmed_by")),
                "尚未确认的推断不能恢复生效；请用 template on 确认")
        template["status"] = "active"
        template["updated"] = now()
        journal(data, "template.resume", template["id"], template["name"] + " 恢复可用")
        return {"template": template}

    return prefs.change(action)


def command_list(prefs, dimension):
    data = prefs.load()
    rows = [t for t in data["templates"] if not dimension or t["dimension"] == dimension]
    return {"templates": rows, "settings": data["settings"],
            "note": "default_on 才是自动生效；其余只在用户点名时使用"}


def command_show(prefs, template_id):
    data = prefs.load()
    return {"template": find(data, template_id)}


def command_query(prefs, scene, model, dimension):
    data = prefs.load()
    view = query_view(data, scene, model, dimension)
    return {"settings": data["settings"], **view,
            "note": "apply 关闭时不得使用；default_fill 只在母版该维度为空时填充；"
                    "avoid 只用于设计排除，不写负向词；pending 不参与设计"}


def command_archive_add(prefs, payload):
    require(type(payload) is dict, "存档输入必须是对象")
    allowed = {"master", "prompt", "rating", "target", "note"}
    unknown = set(payload) - allowed
    require(not unknown, "存档输入包含未知字段: " + ",".join(sorted(unknown)))
    for key in ("master", "prompt", "rating"):
        require(key in payload, "存档输入缺少 " + key)

    def action(data):
        require(data["settings"]["record"], "记录开关已关闭")
        record = {"id": next_id("A", data["archive"]), "master": payload["master"],
                  "prompt": payload["prompt"], "rating": payload["rating"],
                  "target": payload.get("target", "image"),
                  "note": payload.get("note", ""), "time": now()}
        data["archive"].append(record)
        journal(data, "archive.add", record["id"],
                record["rating"] + "｜" + record["target"] + "｜" + str(record["master"].get("master_id")))
        return {"archive": {k: v for k, v in record.items() if k != "master"},
                "master_id": record["master"].get("master_id"),
                "note": "只存档，不建立模板，不影响设计偏好"}

    return prefs.change(action)


def command_infer(prefs, payload):
    require(type(payload) is dict, "推断输入必须是对象")
    require(set(payload) == {"request", "candidates", "basis"}, "推断输入必须为 request/candidates/basis")
    require(type(payload["request"]) is str and payload["request"].strip(), "缺少用户要求原话")
    require(type(payload["candidates"]) is list and payload["candidates"], "候选不能为空")
    require(type(payload["basis"]) is list and
            all(type(x) is str and x.strip() for x in payload["basis"]), "basis 必须是存档 ID 数组")

    def action(data):
        require(data["settings"]["record"], "记录开关已关闭")
        known = {record["id"] for record in data["archive"]}
        missing = [x for x in payload["basis"] if x not in known]
        require(not missing, "依据的存档不存在: " + ",".join(missing))
        created = []
        for candidate in payload["candidates"]:
            require(type(candidate) is dict, "候选必须是对象")
            for key in ("name", "dimension", "attributes", "apply_mode"):
                require(key in candidate, "候选缺少 " + key)
            validate_input_types(candidate)
            template = {
                "id": next_id("T", data["templates"] + created),
                "name": candidate["name"],
                "dimension": candidate["dimension"],
                "attributes": copy.deepcopy(candidate["attributes"]),
                "apply_mode": candidate["apply_mode"],
                "scope": candidate.get("scope", {"scene": "*", "model": "*"}),
                "default_on": False,
                "status": "pending",
                "source": "inferred",
                "source_items": copy.deepcopy(candidate.get("source_items", [])),
                "evidence": list(payload["basis"]),
                "note": "用户要求推断：" + payload["request"],
                "created": now(),
                "updated": now(),
            }
            created.append(template)
        validate_candidates = copy.deepcopy(data)
        validate_candidates["templates"].extend(created)
        validate(validate_candidates)
        data["templates"].extend(created)
        journal(data, "template.infer", ",".join(t["id"] for t in created),
                "用户要求推断，产出 " + str(len(created)) + " 条待确认模板")
        return {"templates": [{k: v for k, v in t.items() if k != "evidence"} for t in created],
                "note": "全部为 pending，经用户确认（on）后才可能生效"}

    return prefs.change(action)


def command_set(prefs, key, value):
    require(key in SETTINGS, "未知设置项；只允许 " + "/".join(SETTINGS))
    require(value in ("on", "off"), "取值只能是 on 或 off")

    def action(data):
        data["settings"][key] = value == "on"
        journal(data, "settings", key, value)
        return {"settings": copy.deepcopy(data["settings"])}

    return prefs.change(action)


def command_init(prefs):
    with prefs.lock():
        if prefs.path.exists():
            data = prefs.load()
            return {"saved": False, "path": str(prefs.path), "note": "已存在，不覆盖",
                    "templates": len(data["templates"]), "archive": len(data["archive"])}
        result = prefs.save(blank())
    return {**result, "note": "已创建空偏好库；模板默认全部关闭"}


def command_status(prefs):
    data = prefs.load()
    defaults = {t["dimension"]: t["id"] for t in data["templates"] if t["default_on"]}
    return {
        "version": VERSION,
        "path": str(prefs.path),
        "exists": prefs.path.exists(),
        "settings": data["settings"],
        "counts": {"templates": len(data["templates"]),
                   "active": sum(t["status"] == "active" for t in data["templates"]),
                   "pending": sum(t["status"] == "pending" for t in data["templates"]),
                   "archive": len(data["archive"])},
        "defaults": defaults,
        "sha256": digest(data)[:12],
        "note": "pending 是推断结果，未确认不参与设计",
    }


# ---------- 入口 ----------

def build_parser():
    parser = argparse.ArgumentParser(description="视觉导演系统 V1.5.3 偏好模板与存档（非自动生图程序）")
    parser.add_argument("--data-dir", required=True, help="源码之外的本地运行数据目录")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="创建空偏好库")
    sub.add_parser("status", help="查看设置、计数与默认模板")

    template = sub.add_parser("template", help="模板维护")
    template_sub = template.add_subparsers(dest="action", required=True)
    add = template_sub.add_parser("add")
    add.add_argument("--input", required=True)
    listing = template_sub.add_parser("list")
    listing.add_argument("--dimension", choices=DIMENSIONS)
    show = template_sub.add_parser("show")
    show.add_argument("--id", required=True)
    for name, help_text in (("on", "设为该维度默认开启"), ("off", "取消默认开启（仍可点名使用）"),
                            ("stop", "停用并保留记录"), ("resume", "恢复可用")):
        item = template_sub.add_parser(name, help=help_text)
        item.add_argument("--id", required=True)
    stop = template_sub.choices["stop"]
    stop.add_argument("--reason", default="")

    query = sub.add_parser("query", help="取本次适用的模板")
    query.add_argument("--scene", default="")
    query.add_argument("--model", default="")
    query.add_argument("--dimension", choices=DIMENSIONS)

    archive = sub.add_parser("archive", help="提示词与母版存档（不影响偏好）")
    archive_sub = archive.add_subparsers(dest="action", required=True)
    archive_add = archive_sub.add_parser("add")
    archive_add.add_argument("--input", required=True)

    infer = sub.add_parser("infer", help="用户要求的偏好推断（产出 pending）")
    infer.add_argument("--input", required=True)

    setting = sub.add_parser("set", help="开关：record / apply / remind")
    setting.add_argument("--key", required=True)
    setting.add_argument("--value", required=True)
    return parser


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    args = build_parser().parse_args()
    prefs = Prefs(args.data_dir)
    if args.command == "init":
        return command_init(prefs), 0
    if args.command == "status":
        return command_status(prefs), 0
    if args.command == "template":
        if args.action == "add":
            result = command_add(prefs, read_json(args.input))
        elif args.action == "list":
            result = command_list(prefs, args.dimension)
        elif args.action == "show":
            result = command_show(prefs, args.id)
        elif args.action == "on":
            result = command_on(prefs, args.id)
        elif args.action == "off":
            result = command_off(prefs, args.id)
        elif args.action == "stop":
            result = command_stop(prefs, args.id, args.reason)
        else:
            result = command_resume(prefs, args.id)
        return result, 0
    if args.command == "query":
        return command_query(prefs, args.scene, args.model, args.dimension), 0
    if args.command == "archive":
        return command_archive_add(prefs, read_json(args.input)), 0
    if args.command == "infer":
        return command_infer(prefs, read_json(args.input)), 0
    return command_set(prefs, args.key, args.value), 0


if __name__ == "__main__":
    try:
        result, code = main()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(code)
    except (PrefsError, ValueError, KeyError, OSError, TypeError) as error:
        print(json.dumps({"saved": False, "error": str(error)}, ensure_ascii=False),
              file=sys.stderr)
        raise SystemExit(1)
