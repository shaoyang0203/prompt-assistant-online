"""Harness persistence and evidence gates. Python 3.10+, standard library only.

All mutations publish immutable generations through one atomic CURRENT pointer.
An exclusive writer lock prevents lost updates; readers see a complete generation.
No imported text is evaluated or executed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from datetime import datetime, timezone
from uuid import uuid4
import zipfile
from contextlib import contextmanager

VERSION = "1.3.0-harness"
SKILL = "prompt-assistant-online-v1-3-0-harness"
PACKAGE = Path(__file__).resolve().parents[1]
FORMAT = 1
RATINGS = ("特别喜欢", "喜欢", "一般", "厌恶")
DEFAULT = {"config_version": 1, "data_version": 1, "enabled": False,
           "min_feedback": 3, "min_scenes": 2, "min_test_pairs": 2,
           "max_regression": 0, "authorized_overrides": False,
           "last_successful_check": None}


class HarnessError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid4().hex


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def require(condition, message):
    if not condition:
        raise HarnessError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic(path, raw):
    path = Path(path)
    temp = path.with_name("." + path.name + "." + uid())
    try:
        with temp.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(temp.read_bytes() == raw, "写后核验失败")
        os.replace(temp, path)
        require(path.read_bytes() == raw, "保存后核验失败")
    finally:
        temp.unlink(missing_ok=True)


def blank():
    return {"config": copy.deepcopy(DEFAULT),
            "user_preferences": {"data_version": 1,
                "settings": {"learning": True, "apply": True},
                "feedback": [], "preferences": [], "constraints": []},
            "learned_overrides": [], "candidates": [], "experiments": [],
            "evolution_log": [], "sessions": {}}


def validate_config(config):
    require(isinstance(config, dict), "配置必须为对象")
    require(set(config) == set(DEFAULT), "配置字段不兼容")
    require(config["config_version"] == 1 and config["data_version"] == FORMAT,
            "配置或数据版本不支持")
    for key in ("enabled", "authorized_overrides"):
        require(type(config[key]) is bool, "配置布尔字段错误: " + key)
    for key in ("min_feedback", "min_scenes", "min_test_pairs"):
        require(type(config[key]) is int and config[key] >= 2, "优化门槛无效: " + key)
    require(type(config["max_regression"]) in (int, float) and
            math.isfinite(config["max_regression"]) and config["max_regression"] >= 0,
            "回归容忍参数无效")
    require(config["last_successful_check"] is None or
            isinstance(config["last_successful_check"], str), "检测时间无效")


def validate_records(data):
    """Validate stored and imported data, including scope and evidence invariants."""
    require(set(data) == set(blank()), "数据类别不兼容")
    validate_config(data["config"])
    prefs = data["user_preferences"]
    require(set(prefs) == {"data_version", "settings", "feedback", "preferences", "constraints"},
            "偏好字段不兼容")
    require(prefs["data_version"] == FORMAT, "偏好格式版本不支持")
    require(set(prefs["settings"]) == {"learning", "apply"} and
            all(type(x) is bool for x in prefs["settings"].values()), "偏好设置无效")
    groups = [prefs[k] for k in ("feedback", "preferences", "constraints")]
    groups += [data[k] for k in ("learned_overrides", "candidates", "experiments", "evolution_log")]
    for records in groups:
        require(isinstance(records, list), "记录集合必须为数组")
        ids = set()
        for record in records:
            require(isinstance(record, dict) and isinstance(record.get("id"), str)
                    and re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", record["id"]), "记录 ID 无效")
            require(record["id"] not in ids, "重复 ID")
            ids.add(record["id"])
    feedback_ids = {f["id"] for f in prefs["feedback"]}
    for f in prefs["feedback"]:
        required = {"id", "prompt_id", "rating", "target", "features", "polarity", "weight",
                    "context", "model", "model_version", "raw", "inference", "inferred",
                    "time", "confirmed", "hard", "prompt", "image_evidence", "scene",
                    "classification"}
        require(set(f) == required, "反馈字段不完整或包含未知字段")
        require(f["rating"] in RATINGS and f["weight"] in ("弱", "中", "强"), "评价或权重无效")
        require(f["polarity"] in ("正向", "负向", "中性"), "反馈方向无效")
        require(all(type(f[k]) is bool for k in ("confirmed", "hard", "inferred")), "反馈标记无效")
        require(isinstance(f["features"], list) and all(isinstance(x, str) and x.strip() for x in f["features"]), "特点无效")
        require(all(isinstance(f[k], str) for k in required - {"features", "confirmed", "hard", "inferred"}), "反馈字段类型无效")
        require(f["classification"] in ("personal", "design", "model"), "反馈分类无效")
        require(not f["inferred"] or f["inference"].strip(), "推测内容不能为空白")
        require(not f["inferred"] or (f["weight"] == "弱" and not f["hard"]), "推断不得强权重或建立硬约束")
    for p in prefs["preferences"] + prefs["constraints"]:
        require(set(p) == {"id", "content", "context", "model", "model_version", "source",
                           "evidence", "status", "hard", "time", "weight", "polarity"}, "偏好字段无效")
        require(isinstance(p["evidence"], list) and set(p["evidence"]) <= feedback_ids, "偏好证据缺失")
        require(p["status"] in ("active", "disabled", "conflict") and type(p["hard"]) is bool, "偏好状态无效")
        require(p["source"] in ("用户明确", "Agent 推断") and p["weight"] in ("弱", "中", "强"), "偏好来源无效")
        require(all(isinstance(p[k], str) for k in ("content", "context", "model", "model_version", "time")), "偏好文本字段无效")
        require(p["content"].strip(), "偏好内容不能为空白")
        require(p["polarity"] in ("正向", "负向", "中性"), "偏好方向无效")
        require(p["source"] != "Agent 推断" or p["weight"] == "弱", "推断偏好只能弱权重")
        require(not p["hard"] or p["source"] == "用户明确", "硬约束必须用户明确")
    for c in data["candidates"]:
        require(set(c) == {"id", "rule", "context", "model", "model_version", "evidence", "goal",
                           "factor", "status", "fingerprint", "time"}, "候选字段无效")
        require(all(isinstance(c[k], str) and c[k].strip() for k in ("rule", "goal", "factor", "context")), "候选内容不能为空白")
        require(c["status"] in ("candidate", "rejected", "active", "rolled_back", "imported_pending"), "候选状态无效")
        require(isinstance(c["evidence"], list), "候选证据无效")
        require(all(isinstance(c[k], str) for k in ("rule", "context", "model", "model_version", "goal", "factor", "fingerprint", "time")), "候选文本字段无效")
    for r in data["learned_overrides"]:
        require(set(r) == {"id", "candidate_id", "rule", "context", "model", "model_version",
                          "experiment_id", "validation_level", "status", "time"}, "经验字段无效")
        require(r["status"] in ("active", "disabled", "imported_pending") and
                r["validation_level"] in ("text", "image"), "经验状态无效")
        require(all(isinstance(v, str) for v in r.values()), "经验文本字段无效")
    for e in data["experiments"]:
        require(set(e) == {"id", "candidate_id", "pairs", "criteria", "passed", "level", "time"}, "实验字段无效")
        require(type(e["passed"]) is bool and e["level"] in ("text", "image"), "实验结论无效")
        validate_pairs(e["pairs"])
        require(all(isinstance(e[k], str) for k in ("candidate_id", "criteria", "time")), "实验文本字段无效")
    for log in data["evolution_log"]:
        require(set(log) == {"id", "time", "source_version", "object", "before", "after", "reason",
                            "source_ids", "goal", "test_tasks", "criteria", "results", "accepted",
                            "effective", "rollback", "rollback_reason"}, "日志字段无效")
        require(all(type(log[k]) is bool for k in ("accepted", "effective", "rollback")), "日志状态无效")
    require(isinstance(data["sessions"], dict), "会话状态无效")


def validate_pairs(pairs):
    require(isinstance(pairs, list), "测试对必须为数组")
    for p in pairs:
        require(set(p) == {"task_id", "scene", "baseline", "candidate", "before", "after",
                          "hard_requirements_preserved", "creative_space_preserved", "evidence"}, "测试对字段无效")
        require(all(isinstance(p[k], str) and p[k].strip() for k in
                    ("task_id", "scene", "baseline", "candidate", "evidence")), "测试缺少任务、文本或证据")
        require(all(type(p[k]) in (float, int) and 0 <= p[k] <= 1
                    for k in ("before", "after")), "测试评分须为 0 到 1")
        require(all(type(p[k]) is bool for k in ("hard_requirements_preserved", "creative_space_preserved")),
                "测试保护项无效")


def migrate_format(data, version):
    """Explicit version dispatch. Unsupported formats never overwrite current data."""
    require(type(version) is int and version == 1, "不支持的数据版本；需要显式迁移适配器")
    result = copy.deepcopy(data)
    validate_records(result)
    return result


def log_event(data, obj, before, after, reason, source_ids=None, goal="", experiment=None,
              accepted=True, effective=True, rollback=False):
    e = experiment or {}
    data["evolution_log"].append({"id": uid(), "time": now(), "source_version": VERSION,
        "object": obj, "before": before, "after": after, "reason": reason,
        "source_ids": source_ids or [], "goal": goal, "test_tasks": e.get("pairs", []),
        "criteria": e.get("criteria", ""), "results": e,
        "accepted": accepted, "effective": effective, "rollback": rollback,
        "rollback_reason": reason if rollback else ""})


def preference_key(record):
    return tuple(record[k] for k in ("content", "context", "model", "model_version"))


def preference_conflicts(prefs):
    records = [p for key in ("preferences", "constraints") for p in prefs[key]
               if p["status"] != "disabled"]
    groups = {}
    for p in records:
        groups.setdefault(preference_key(p), []).append(p)
    for group in groups.values():
        if {"正向", "负向"} <= {p["polarity"] for p in group}:
            for p in group:
                if p["polarity"] in ("正向", "负向"):
                    p["status"] = "conflict"


def add_preference(prefs, record, category):
    for existing in prefs[category]:
        if (existing["status"] != "disabled" and
                preference_key(existing) == preference_key(record) and
                all(existing[k] == record[k] for k in ("polarity", "source", "hard"))):
            existing["evidence"] = list(dict.fromkeys(existing["evidence"] + record["evidence"]))
            ranks = {"弱": 0, "中": 1, "强": 2}
            if ranks[record["weight"]] > ranks[existing["weight"]]:
                existing["weight"] = record["weight"]
            if record["status"] == "conflict":
                existing["status"] = "conflict"
            return False
    prefs[category].append(record)
    return True


class Store:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("PROMPT_HARNESS_DATA_DIR") or
                         Path.home() / ".prompt-assistant" / "harness").expanduser().resolve()
        require(not self.root.is_relative_to(PACKAGE), "数据目录不得位于官方 Skill 内")
        source = PACKAGE.parent / "V1.2.0-VIP"
        require(not self.root.is_relative_to(source.resolve()), "数据目录不得位于 VIP 基线内")

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ".writer.lock"
        try:
            stream = path.open("x", encoding="utf-8")
        except FileExistsError:
            raise HarnessError("数据正在写入或有遗留锁；核实没有写入进程后再手动移除锁")
        try:
            with stream:
                stream.write(str(os.getpid()))
            yield
        finally:
            path.unlink()

    def _journal_path(self, generation=None):
        pointer = self.root / "CURRENT"
        generation = generation or (pointer.read_text(encoding="utf-8").strip() if pointer.exists() else "initial")
        require(generation == "initial" or re.fullmatch(r"[0-9a-f]{32}", generation), "CURRENT 指针损坏")
        return self.root / "audit" / (generation + ".json")

    def _with_local_state(self, data, generation):
        health = self.root / "health.json"
        if health.exists():
            value = read_json(health)
            require(set(value) == {"last_successful_check"} and
                    isinstance(value["last_successful_check"], str), "健康状态文件无效")
            data["config"]["last_successful_check"] = value["last_successful_check"]
        journal = self._journal_path(generation)
        if journal.exists():
            events = read_json(journal)
            require(isinstance(events, list), "审计日志格式无效")
            data["evolution_log"].extend(events)
        validate_records(data)
        return data

    def _commit(self, data, original):
        validate_records(data)
        if data == original:
            return False
        if ({k: v for k, v in data.items() if k != "evolution_log"} ==
                {k: v for k, v in original.items() if k != "evolution_log"} and
                data["evolution_log"][:len(original["evolution_log"])] == original["evolution_log"]):
            path = self._journal_path()
            events = read_json(path) if path.exists() else []
            events.extend(data["evolution_log"][len(original["evolution_log"]):])
            path.parent.mkdir(exist_ok=True)
            atomic(path, encoded(events))
        else:
            self.save(data)
        return True

    def load(self):
        self._repair_needed = False
        pointer = self.root / "CURRENT"
        if not pointer.exists():
            generations = self.root / "generations"
            require(not generations.exists() or (generations.is_dir() and not any(generations.iterdir())),
                    "检测到未完成初始化，需检查 generations 后恢复")
            return self._with_local_state(blank(), "initial")
        name = pointer.read_text(encoding="utf-8").strip()
        require(re.fullmatch(r"[0-9a-f]{32}", name), "CURRENT 指针损坏")
        folder = self.root / "generations" / name
        result = {k: read_json(folder / (k + ".json")) for k in
                  ("user_preferences", "learned_overrides", "candidates", "sessions")}
        try:
            result["config"] = read_json(folder / "config.json")
            validate_config(result["config"])
        except (ValueError, OSError, TypeError, KeyError):
            result["config"] = copy.deepcopy(DEFAULT)
            result["config"]["_repair_needed"] = True
        result["experiments"] = [read_json(p) for p in sorted((folder / "experiments").glob("*.json"))]
        result["evolution_log"] = [json.loads(line) for line in
                                   (folder / "evolution_log.jsonl").read_text(encoding="utf-8").splitlines() if line]
        config = result["config"]
        if config.pop("_repair_needed", False):
            result["config"] = config
            self._repair_needed = True
            # Preserved corrupt generation remains available for recovery.
            log_event(result, "config", "损坏配置保留在旧 generation", config,
                      "修复为默认关闭；保留其他数据")
        return self._with_local_state(result, name)

    def save(self, data):
        validate_records(data)
        folder = self.root / "generations" / uid()
        folder.mkdir(parents=True)
        try:
            for key in ("config", "user_preferences", "learned_overrides", "candidates", "sessions"):
                atomic(folder / (key + ".json"), encoded(data[key]))
            (folder / "experiments").mkdir()
            for e in data["experiments"]:
                atomic(folder / "experiments" / (e["id"] + ".json"), encoded(e))
            atomic(folder / "evolution_log.jsonl", b"".join(encoded(e).replace(b"\n", b"") + b"\n"
                   for e in data["evolution_log"]))
            # Verify the new pointer before publication; replace is the final commit point.
            # A failed post-replace read must not turn a committed deletion into a reported failure.
            pointer = folder / ".pointer"
            atomic(pointer, folder.name.encode("utf-8"))
            os.replace(pointer, self.root / "CURRENT")
        except BaseException:
            # Never remove a published generation if verification after replace failed.
            current = (self.root / "CURRENT").read_text() if (self.root / "CURRENT").exists() else ""
            if current != folder.name:
                shutil.rmtree(folder)
            raise

    def change(self, action, audit_rejections=True):
        with self.lock():
            data = self.load()
            original = copy.deepcopy(data)
            try:
                result = action(data)
                validate_records(data)
            except HarnessError as exc:
                if audit_rejections:
                    rejected = copy.deepcopy(original)
                    log_event(rejected, "rejected_operation", "未应用", "未应用", str(exc),
                              accepted=False, effective=False)
                    self._commit(rejected, original)
                raise
            self._commit(data, original)
            return result

    def probe(self, create=False, capability=True):
        temp = None
        reason = ""
        try:
            require(capability, "没有可用的文件写入或执行工具")
            if not self.root.exists():
                require(create, "Harness 数据目录不存在；需明确初始化")
                self.root.mkdir(parents=True)
            require(self.root.is_dir(), "Harness 数据目录不是目录")
            temp = self.root / (".probe-" + uid())
            raw = os.urandom(48)
            with temp.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            require(temp.read_bytes() == raw, "写入成功但重新读取核验失败")
        except (OSError, HarnessError) as exc:
            reason = str(exc)
        finally:
            if temp and temp.exists():
                try:
                    temp.unlink()
                except OSError as exc:
                    reason += "; 临时文件清理失败: " + str(exc)
        if not reason:
            try:
                with self.lock():
                    data = self.load()
                    if not (self.root / "CURRENT").exists() or self._repair_needed:
                        self.save(data)
                    atomic(self.root / "health.json", encoded({"last_successful_check": now()}))
                    data = self.load()
                require(data["config"]["last_successful_check"], "健康状态保存验证失败")
                return {"status": "开" if data["config"]["enabled"] else "关",
                        "available": True, "reason": "已实际写入、同步、重读并清理；业务数据校验通过，健康状态独立保存",
                        "data_dir": str(self.root)}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                reason = "无法可靠保存配置或数据: " + str(exc)
        return {"status": "不可用", "available": False, "reason": reason,
                "data_dir": str(self.root)}

    def start(self, session, create=False):
        require(isinstance(session, str) and 0 < len(session) <= 200, "需要稳定的当前对话 ID")
        status = self.probe(create=create)
        first = True
        if status["available"]:
            def action(data):
                nonlocal first
                first = session not in data["sessions"]
                if first:
                    data["sessions"][session] = {"started": now(), "asked": True}
            self.change(action)
        lines = (["正在调用提示词助手 V1.3.0 Harness"] if first else [])
        lines.append("[递归优化 --" + status["status"] + "]")
        if first:
            lines.append("递归优化会收集反馈，经对照与跨题材验证后更新独立经验；个人偏好与核心设计分离。")
            if status["available"]:
                lines.append("本次是否开启递归优化引擎？未回答时保留当前状态，首次安装默认关闭。")
            else:
                lines.append(status["reason"] + "。本轮可继续设计，反馈仅在对话中暂存，未可靠持久化。")
        return {**status, "first": first, "text": "\n".join(lines)}

    def toggle(self, enabled):
        status = self.probe()
        require(status["available"], status["reason"])
        def action(data):
            before = data["config"]["enabled"]
            data["config"]["enabled"] = enabled
            if before != enabled:
                log_event(data, "config.enabled", before, enabled, "用户明确切换递归优化")
        self.change(action)
        require(self.load()["config"]["enabled"] == enabled, "开关保存失败")
        return {"status": "开" if enabled else "关", "saved": True}

    def feedback(self, **input_data):
        allowed = {"prompt_id", "rating", "target", "features", "context", "model", "model_version",
                   "raw", "inference", "confirmed", "permanent", "hard_confirmed", "long_term",
                   "cross_model", "prompt", "image_evidence", "scene", "classification", "polarity"}
        require(set(input_data) <= allowed, "未知反馈字段")
        q = input_data
        for flag in ("confirmed", "permanent", "hard_confirmed", "long_term", "cross_model"):
            require(flag not in q or type(q[flag]) is bool, "反馈标记必须为布尔值: " + flag)
        require(q.get("rating") in RATINGS and q.get("prompt_id") and q.get("raw"), "缺少评价、方案 ID 或原话")
        features = q.get("features", [])
        require(isinstance(features, list) and all(isinstance(x, str) and x.strip() for x in features), "特点应为非空白文本数组")
        inference = q.get("inference", "")
        require(isinstance(inference, str) and (not inference or inference.strip()), "推测内容不能为空白")
        require(not inference or not features, "用户明确特点与 Agent 推断须分开记录")
        require(not q.get("long_term") or q.get("confirmed") or inference,
                "长期明确偏好需要用户确认")
        hard = bool(q.get("permanent") or q.get("hard_confirmed"))
        require(not hard or (features and q.get("confirmed") and not inference), "硬约束需要用户明确确认具体内容")
        polarity = q.get("polarity") or ("正向" if q["rating"] in RATINGS[:2] else
                                         "负向" if q["rating"] == "厌恶" else "中性")
        weight = "弱" if inference or not features or polarity == "中性" else (
                 "强" if q["rating"] in ("特别喜欢", "厌恶") else "中")
        f = {"id": uid(), "prompt_id": q["prompt_id"], "rating": q["rating"],
             "target": q.get("target", "prompt"), "features": features, "polarity": polarity,
             "weight": weight, "context": q.get("context", "当前方案"), "model": q.get("model", "未知"),
             "model_version": q.get("model_version", "未知"), "raw": q["raw"], "inference": inference,
             "inferred": bool(inference), "time": now(), "confirmed": q.get("confirmed", False),
             "hard": hard, "prompt": q.get("prompt", "原文不可获取"),
             "image_evidence": q.get("image_evidence", "未提供"), "scene": q.get("scene", "未知"),
             "classification": q.get("classification", "personal")}
        def action(data):
            prefs = data["user_preferences"]
            if not prefs["settings"]["learning"]:
                return {"saved": False, "reason": "VIP 自动学习已暂停"}
            prefs["feedback"].append(f)
            # A rating is not a feature. Temporary feedback does not become a lasting preference.
            if (features or inference) and (q.get("long_term") or hard):
                for content in features or [inference]:
                    p = {"id": uid(), "content": content, "context": f["context"],
                         "model": "*" if q.get("cross_model") else f["model"],
                         "model_version": "*" if q.get("cross_model") else f["model_version"],
                         "source": "Agent 推断" if inference else "用户明确", "evidence": [f["id"]],
                         "status": "active", "hard": hard, "time": now(), "weight": weight,
                         "polarity": polarity}
                    add_preference(prefs, p, "constraints" if hard else "preferences")
                preference_conflicts(prefs)
            log_event(data, "feedback", None, f["id"], "保存用户反馈；评价强度与具体特点分别记录", [f["id"]])
            return {"saved": True, "feedback": f, "clarify": not features and f["rating"] in ("特别喜欢", "厌恶")}
        return self.change(action)

    def applicable(self, context, model, model_version="未知", current_features=()):
        data = self.load()
        prefs = data["user_preferences"]
        preference_conflicts(prefs)
        def in_scope(record):
            return (record["context"] in (context, "*") and record["model"] in (model, "*")
                    and record["model_version"] in (model_version, "*"))
        def matches(record):
            return (record["status"] == "active" and record["context"] in (context, "*") and
                    record["model"] in (model, "*") and record["model_version"] in (model_version, "*"))
        constraints = [p for p in prefs["constraints"] if matches(p)]
        ordinary = [p for p in prefs["preferences"] if matches(p) and p["content"] not in current_features]
        return {"preferences": ordinary if prefs["settings"]["apply"] else [],
                "constraints": constraints,
                "conflicts": [p for p in prefs["preferences"] + prefs["constraints"]
                              if in_scope(p) and (p["status"] == "conflict" or
                                  (p in constraints and p["content"] in current_features))],
                "overrides": [r for r in data["learned_overrides"] if matches(r)]}

    def candidate(self, rule, evidence, goal, factor, context, model="*", model_version="*"):
        def action(data):
            config = data["config"]
            require(config["enabled"], "递归优化已关闭")
            require(all(isinstance(x, str) and x.strip() for x in (rule, goal, factor, context)), "候选需规则、目标、单一主要因素与语境")
            fingerprint = digest(encoded([rule, context, model, model_version, factor]))
            require(not any(c["fingerprint"] == fingerprint for c in data["candidates"]),
                    "相同候选已尝试；失败假设需提供新的主要因素或不同方案")
            records = {f["id"]: f for f in data["user_preferences"]["feedback"]}
            require(set(evidence) <= set(records), "来源反馈不存在")
            selected = [records[i] for i in set(evidence)]
            require(all(f["classification"] == "design" and f["features"] and f["confirmed"]
                        and not f["inferred"] for f in selected), "个人喜好或模型缺陷不得直接转成通用设计经验")
            require(len({f["prompt_id"] for f in selected}) >= config["min_feedback"] and
                    len({f["scene"] for f in selected if f["scene"] != "未知"}) >= config["min_scenes"],
                    "未达到独立反馈与场景门槛")
            require(all(model == "*" or f["model"] == model for f in selected), "证据模型范围不符")
            require(all(model_version == "*" or f["model_version"] == model_version for f in selected), "证据模型版本范围不符")
            c = {"id": uid(), "rule": rule, "context": context, "model": model,
                 "model_version": model_version, "evidence": list(set(evidence)), "goal": goal,
                 "factor": factor, "status": "candidate", "fingerprint": fingerprint, "time": now()}
            data["candidates"].append(c)
            log_event(data, "candidate", None, c, "达到候选门槛；尚未生效", evidence, goal, effective=False)
            return c
        return self.change(action)

    def experiment(self, candidate_id, pairs, criteria, level="text"):
        validate_pairs(pairs)
        require(level in ("text", "image") and isinstance(criteria, str) and criteria.strip(), "需测试层级和评价标准")
        def action(data):
            config = data["config"]
            require(config["enabled"], "递归优化已关闭")
            c = next((c for c in data["candidates"] if c["id"] == candidate_id), None)
            require(c and c["status"] == "candidate", "候选不存在或已处理")
            records = {f["id"]: f for f in data["user_preferences"]["feedback"]}
            source_scenes = {records[i]["scene"] for i in c["evidence"]}
            source_tasks = {records[i]["prompt_id"] for i in c["evidence"]}
            task_ids = {p["task_id"] for p in pairs}
            require(len(task_ids) == len(pairs), "同一任务不能重复计数")
            holdout = any(p["scene"] not in source_scenes and p["task_id"] not in source_tasks for p in pairs)
            enough = len(task_ids) >= config["min_test_pairs"] and len({p["scene"] for p in pairs}) >= 2
            preserved = all(p["hard_requirements_preserved"] and p["creative_space_preserved"] for p in pairs)
            stable = all(p["after"] + config["max_regression"] >= p["before"] for p in pairs)
            improved = any(p["after"] > p["before"] for p in pairs)
            if level == "image":
                require(all(p["evidence"].startswith(("image:", "user-feedback:")) for p in pairs),
                        "实际出图测试须可定位图像或用户反馈证据")
            passed = bool(holdout and enough and preserved and stable and improved)
            e = {"id": uid(), "candidate_id": c["id"], "pairs": pairs, "criteria": criteria,
                 "passed": passed, "level": level, "time": now()}
            data["experiments"].append(e)
            if passed and config["authorized_overrides"]:
                c["status"] = "active"
                data["learned_overrides"].append({"id": uid(), "candidate_id": c["id"], "rule": c["rule"],
                    "context": c["context"], "model": c["model"], "model_version": c["model_version"],
                    "experiment_id": e["id"], "validation_level": level, "status": "active", "time": now()})
            elif not passed:
                c["status"] = "rejected"
            log_event(data, "learned_overrides", "候选未生效", c["status"],
                      "通过对照和留出题材验证" if passed else "拒绝晋级：门槛、退化或保护项不通过",
                      c["evidence"], c["goal"], e, accepted=passed, effective=c["status"] == "active")
            return {"experiment": e, "candidate_status": c["status"],
                    "claim": "仅文本级验证；未证明实际出图提升" if level == "text" else "依据所提供的出图证据评估；未证明普遍因果"}
        return self.change(action)

    def configure(self, values):
        require(set(values) <= {"min_feedback", "min_scenes", "min_test_pairs", "max_regression"},
                "仅允许修改优化门槛和测试参数")
        def action(data):
            before = copy.deepcopy(data["config"])
            data["config"].update(values)
            validate_config(data["config"])
            if before != data["config"]:
                log_event(data, "config.thresholds", before, data["config"], "用户配置优化和测试门槛")
            return copy.deepcopy(data["config"])
        return self.change(action)

    def rollback(self, rule_id, reason):
        require(isinstance(reason, str) and reason.strip(), "需回滚原因")
        def action(data):
            r = next((r for r in data["learned_overrides"] if r["id"] == rule_id), None)
            require(r and r["status"] == "active", "没有生效的目标经验")
            before = copy.deepcopy(r)
            r["status"] = "disabled"
            for c in data["candidates"]:
                if c["id"] == r["candidate_id"]:
                    c["status"] = "rolled_back"
            log_event(data, "learned_overrides", before, r, reason, [r["candidate_id"]], rollback=True)
        return self.change(action)

    def manage(self, operation, record_id=None, value=None, confirm=False):
        """Manage current records atomically; history and backups are never purged here."""
        if operation == "forget":
            require(isinstance(record_id, str) and record_id.strip(), "forget 必须提供目标 ID")
        def action(data):
            before = copy.deepcopy(data)
            prefs = data["user_preferences"]
            if operation in ("learning", "apply"):
                require(type(value) is bool, "设置需要布尔值")
                prefs["settings"][operation] = value
            elif operation == "authorize":
                require(type(value) is bool and confirm is True, "可变经验写入授权需用户明确确认")
                data["config"]["authorized_overrides"] = value
            elif operation in ("disable", "correct"):
                p = next((p for p in prefs["preferences"] + prefs["constraints"] if p["id"] == record_id), None)
                require(p, "偏好不存在")
                require(not p["hard"] or confirm is True, "永久硬约束需用户明确确认后修改或撤销")
                if operation == "disable":
                    p["status"] = "disabled"
                else:
                    require(isinstance(value, str) and value.strip(), "需修正内容")
                    p["content"] = value
                    p["source"] = "用户明确"
                    preference_conflicts(prefs)
            elif operation in ("forget", "clear"):
                require(confirm is True, "删除数据需明确用户请求")
                if operation == "clear":
                    for key in ("feedback", "preferences", "constraints"):
                        prefs[key] = []
                    for key in ("candidates", "experiments", "learned_overrides", "evolution_log"):
                        data[key] = []
                else:
                    records = prefs["preferences"] + prefs["constraints"]
                    target = next((p for p in records if p["id"] == record_id), None)
                    feedback = next((f for f in prefs["feedback"] if f["id"] == record_id), None)
                    require(target is not None or feedback is not None, "目标 ID 不存在；未修改数据")
                    # Shared feedback must remain available to other preference records.
                    shared = {fid for p in records if p["id"] != record_id for fid in p["evidence"]}
                    removed = {record_id}
                    ids = (set(target["evidence"]) - shared) if target is not None else {record_id}
                    removed.update(ids)
                    prefs["feedback"] = [f for f in prefs["feedback"] if f["id"] not in ids]
                    for key in ("preferences", "constraints"):
                        kept = []
                        for p in prefs[key]:
                            if p["id"] == record_id:
                                continue
                            affected = bool(set(p["evidence"]) & ids)
                            p["evidence"] = [fid for fid in p["evidence"] if fid not in ids]
                            if affected and not p["evidence"]:
                                removed.add(p["id"])
                            else:
                                kept.append(p)
                        prefs[key] = kept
                    candidate_ids = {c["id"] for c in data["candidates"] if set(c["evidence"]) & ids}
                    experiment_ids = {e["id"] for e in data["experiments"] if e["candidate_id"] in candidate_ids}
                    rule_ids = {r["id"] for r in data["learned_overrides"]
                                if r["candidate_id"] in candidate_ids or r["experiment_id"] in experiment_ids}
                    removed.update(candidate_ids | experiment_ids | rule_ids)
                    for key in ("candidates", "experiments", "learned_overrides"):
                        data[key] = [r for r in data[key] if r["id"] not in removed]
                    def references_removed(value):
                        if isinstance(value, str):
                            return value in removed
                        if isinstance(value, list):
                            return any(references_removed(x) for x in value)
                        if isinstance(value, dict):
                            return any(references_removed(x) for x in value.values())
                        return False
                    data["evolution_log"] = [e for e in data["evolution_log"] if not references_removed(e)]
            else:
                raise HarnessError("未知管理操作")
            changed = data != before
            if changed:
                log_event(data, "preferences.settings" if operation in ("learning", "apply") else operation,
                          "用户请求前", "用户请求后", "用户明确管理当前数据；删除内容不进入日志")
            return {"saved": changed, "operation": operation,
                    "history_preserved": True} if operation in ("forget", "clear") else {"saved": changed, "operation": operation}
        return self.change(action, audit_rejections=False)


def clarify_unexpected(element, origin, options, selected=None, explicit=None):
    require(origin in ("user", "prompt_omission", "model_added", "unknown"), "需区分偏差来源")
    if explicit:
        return {"action": explicit, "permanent": False, "wait": False}
    require(2 <= len(options) <= 3 and all(isinstance(x, str) for x in options), "需两到三个当前场景选项")
    if selected is None:
        return {"element": element, "origin": origin, "options": options, "wait": True, "permanent": False}
    require(type(selected) is int and 0 <= selected < len(options), "选项无效")
    return {"action": options[selected], "wait": False, "permanent": False}


def data_files(data, kind):
    files = {}
    if kind in ("preferences", "full"):
        files["user_preferences.json"] = encoded(data["user_preferences"])
    if kind in ("harness", "full"):
        for key in ("learned_overrides", "candidates"):
            files[key + ".json"] = encoded(data[key])
        files["evolution_log.jsonl"] = b"".join(json.dumps(x, ensure_ascii=False).encode("utf-8") + b"\n"
                                                  for x in data["evolution_log"])
        for e in data["experiments"]:
            files["experiments/" + e["id"] + ".json"] = encoded(e)
    return files


def export_data(store, output, kind="full"):
    require(kind in ("preferences", "harness", "full"), "导出类别无效")
    data = store.load()
    output = Path(output).resolve()
    require(not output.is_relative_to(PACKAGE), "导出私人数据不得放入官方包内")
    require(not output.is_relative_to((PACKAGE.parent / "V1.2.0-VIP").resolve()), "导出不得写入 VIP 基线")
    require(not output.exists(), "导出路径已存在，拒绝覆盖")
    files = data_files(data, kind)
    if kind == "preferences":
        atomic(output, files["user_preferences.json"])
        validate_preference_file(read_json(output))
    else:
        manifest = {"source_skill": SKILL, "source_version": VERSION, "data_version": FORMAT,
                    "export_time": now(), "categories": sorted(files), "kind": kind,
                    "counts": {k: len(data[k]) for k in ("learned_overrides", "candidates", "experiments", "evolution_log")},
                    "sha256": {k: digest(v) for k, v in files.items()}}
        manifest["counts"]["feedback"] = len(data["user_preferences"]["feedback"]) if kind == "full" else 0
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "export.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", encoded(manifest))
                for name, raw in files.items():
                    z.writestr(name, raw)
            load_archive(archive)
            atomic(output, archive.read_bytes())
    return {"path": str(output), "kind": kind, "sha256": digest(output.read_bytes())}


def validate_preference_file(prefs):
    data = blank()
    data["user_preferences"] = prefs
    validate_records(data)


def load_archive(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) and len(names) <= 10000, "重复条目或文件过多")
        require(sum(i.file_size for i in z.infolist()) <= 50_000_000, "包展开后过大")
        require("manifest.json" in names, "缺少 manifest.json")
        for name in names:
            require(name in ("manifest.json", "user_preferences.json", "learned_overrides.json", "candidates.json", "evolution_log.jsonl") or
                    re.fullmatch(r"experiments/[a-zA-Z0-9_-]{1,100}\.json", name), "包包含不允许的路径或代码: " + name)
        m = json.loads(z.read("manifest.json"))
        require(set(m) == {"source_skill", "source_version", "data_version", "export_time", "categories", "kind", "counts", "sha256"}, "清单字段无效")
        supported_sources = {"1.2.0-harness": "prompt-assistant-online-v1-2-0-harness",
                             "1.2.1-harness": "prompt-assistant-online-v1-2-1-harness",
                             "1.22": "prompt-assistant-online-v1-22-harness",
                             VERSION: SKILL}
        require(isinstance(m["source_version"], str) and
                m["source_version"] in supported_sources and
                m["source_skill"] == supported_sources[m["source_version"]],
                "来源版本不支持，需显式迁移适配器")
        require(m["data_version"] == FORMAT and m["kind"] in ("harness", "full"), "数据版本或包类型不支持")
        expected = {"learned_overrides.json", "candidates.json", "evolution_log.jsonl"}
        require(expected <= set(names) and (m["kind"] != "full" or "user_preferences.json" in names), "缺少必需数据")
        require(set(m["categories"]) == set(names) - {"manifest.json"} == set(m["sha256"]), "清单文件集合不符")
        raw = {n: z.read(n) for n in m["sha256"]}
        require(all(digest(raw[n]) == m["sha256"][n] for n in raw), "文件校验失败")
    data = blank()
    for key in ("user_preferences", "learned_overrides", "candidates"):
        if key + ".json" in raw:
            data[key] = json.loads(raw[key + ".json"])
    data["experiments"] = [json.loads(value) for name, value in sorted(raw.items()) if name.startswith("experiments/")]
    data["evolution_log"] = [json.loads(line) for line in raw["evolution_log.jsonl"].decode("utf-8").splitlines() if line]
    data = migrate_format(data, m["data_version"])
    candidates = {c["id"]: c for c in data["candidates"]}
    experiments = {e["id"]: e for e in data["experiments"]}
    for e in experiments.values():
        require(e["candidate_id"] in candidates, "实验关联候选缺失")
    for r in data["learned_overrides"]:
        require(r["candidate_id"] in candidates and r["experiment_id"] in experiments,
                "经验关联候选或实验缺失")
        e = experiments[r["experiment_id"]]
        c = candidates[r["candidate_id"]]
        require(e["passed"] and e["candidate_id"] == c["id"] and r["rule"] == c["rule"]
                and r["validation_level"] == e["level"], "经验未通过关联验收或内容不符")
    counts = {k: len(data[k]) for k in ("learned_overrides", "candidates", "experiments", "evolution_log")}
    counts["feedback"] = len(data["user_preferences"]["feedback"])
    require(m["counts"] == counts, "清单记录数量不符")
    return data, m


def verify_imported_data(expected, actual):
    """Compare experiment files by unique ID, preserving all content checks.

    Their list order is not persisted: load() orders files by filename, while
    import merges append new records. Other arrays (especially logs) stay ordered.
    Validate before indexing so duplicate IDs cannot be silently discarded.
    """
    validate_records(expected)
    validate_records(actual)
    expected_by_id = {record["id"]: record for record in expected["experiments"]}
    actual_by_id = {record["id"]: record for record in actual["experiments"]}
    require({**expected, "experiments": expected_by_id} ==
            {**actual, "experiments": actual_by_id}, "导入后数据核验失败")


def import_data(store, path):
    path = Path(path)
    if path.suffix.lower() == ".json":
        incoming = blank()
        incoming["user_preferences"] = read_json(path)
        validate_records(incoming)
        kind = "preferences"
    else:
        incoming, manifest = load_archive(path)
        kind = manifest["kind"]
    conflicts = []
    added = {}
    # Backup and merge under the same writer lock, preventing races.
    with store.lock():
        current = store.load()
        original_state = copy.deepcopy(current)
        backup = store.root / ("backup-" + uid() + ".zip")
        export_data(store, backup)
        old_feedback = {r["id"]: r for r in current["user_preferences"]["feedback"]}
        feedback_conflicts = {r["id"] for r in incoming["user_preferences"]["feedback"]
                              if r["id"] in old_feedback and r != old_feedback[r["id"]]}
        old_candidates = {r["id"]: r for r in current["candidates"]}
        candidate_conflicts = {r["id"] for r in incoming["candidates"] if r["id"] in old_candidates
                              and any(old_candidates[r["id"]][k] != r[k] for k in r if k != "status")}
        candidate_conflicts |= {r["id"] for r in incoming["candidates"]
                                if set(r["evidence"]) & feedback_conflicts}
        old_experiments = {r["id"]: r for r in current["experiments"]}
        experiment_conflicts = {r["id"] for r in incoming["experiments"] if r["id"] in old_experiments
                                and r != old_experiments[r["id"]]}
        experiment_conflicts |= {r["id"] for r in incoming["experiments"] if r["candidate_id"] in candidate_conflicts}
        for key in ("feedback", "preferences", "constraints", "learned_overrides", "candidates", "experiments", "evolution_log"):
            target = current["user_preferences"][key] if key in ("feedback", "preferences", "constraints") else current[key]
            source = incoming["user_preferences"][key] if key in ("feedback", "preferences", "constraints") else incoming[key]
            existing = {r["id"]: r for r in target}
            added[key] = 0
            for original in source:
                record = copy.deepcopy(original)
                dependency_conflict = ((key in ("preferences", "constraints", "candidates") and
                                        bool(set(record["evidence"]) & feedback_conflicts)) or
                    (key == "experiments" and record["id"] in experiment_conflicts) or
                    (key == "learned_overrides" and (record["candidate_id"] in candidate_conflicts or
                                                    record["experiment_id"] in experiment_conflicts)))
                if dependency_conflict:
                    conflicts.append({"category": key, "id": record["id"], "reason": "依赖反馈、候选或实验内容冲突，跳过以保留本地证据链"})
                    continue
                if key == "candidates" and record["status"] in ("candidate", "active"):
                    record["status"] = "imported_pending"
                if key == "learned_overrides" and record["status"] == "active":
                    # Import validated user rules, but never silently supersede a conflicting local rule.
                    conflict = any(r["status"] == "active" and r["context"] == record["context"] and
                                   r["model"] == record["model"] and r["rule"] != record["rule"] for r in target)
                    if conflict:
                        record["status"] = "imported_pending"
                        conflicts.append({"category": key, "id": record["id"], "reason": "同范围规则不同，等待用户解决"})
                if record["id"] in existing:
                    # Imported active candidates are intentionally downgraded; compare with original too.
                    if existing[record["id"]] not in (record, original):
                        conflicts.append({"category": key, "id": record["id"], "reason": "同 ID 内容不同，保留本地"})
                    continue
                if key in ("preferences", "constraints"):
                    if not add_preference(current["user_preferences"], record, key):
                        continue
                else:
                    target.append(record)
                existing[record["id"]] = record
                added[key] += 1
        # Harness-only archives intentionally have no private feedback; their references stay historical.
        preference_conflicts(current["user_preferences"])
        for key in ("preferences", "constraints"):
            for record in current["user_preferences"][key]:
                if record["status"] == "conflict":
                    conflicts.append({"category": key, "id": record["id"], "reason": "同范围偏好方向冲突，等待确认"})
        if kind != "preferences":
            current["config"]["enabled"] = False
            current["config"]["authorized_overrides"] = False
            current["sessions"] = {}
        log_event(current, "migration", "已备份", added,
                  "仅导入偏好；保留本地设置和会话" if kind == "preferences" else "导入经验或完整包；保留本地门槛并关闭引擎和授权，重置会话",
                  accepted=True)
        validate_records(current)
        store._commit(current, original_state)
        verify_imported_data(current, store.load())
    status = ({"status": "开" if current["config"]["enabled"] else "关",
               "available": None, "reason": "偏好导入未改动健康状态；需要时单独检测"}
              if kind == "preferences" else store.probe())
    return {"added": added, "conflicts": conflicts, "backup": str(backup), "environment": status,
            "kind": kind, "notice": ("仅合并偏好；本地设置、授权、会话和健康状态保留" if kind == "preferences"
                                      else "历史文本仅为数据；引擎和授权关闭，下次首次调用重新询问启用")}
