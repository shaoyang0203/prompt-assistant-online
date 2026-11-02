"""Master rendering and immutable revision checks."""
from contracts import ZONES, digest, impact, require, validate_master

SOURCES = {"user_specified": "用户指定", "model_added": "模型补充", "jointly_formed": "共同形成"}
STRENGTH = {"hard_constraint": "硬性约束", "confirmed_design": "已确认设计", "adjustable_design": "可调整设计"}

def latest(state):
    require(bool(state["masters"]), "尚未创建视觉母版")
    return state["masters"][-1]

def display_value(item):
    value = item["value"]
    if item["kind"] == "aspect_ratio":
        return str(value["width"]) + ":" + str(value["height"])
    if item["kind"] == "image_text":
        return "画面文字原样预览：\n" + value["literal"] + "\n文字外观：" + value["appearance"]
    return value

def render(master, approved=False):
    validate_master(master)
    lines = ["视觉母版 " + master["master_id"] + " / v" + str(master["revision"]),
             "整版状态：" + ("已确认" if approved else "待用户确认"),
             "确认对象为此完整版本；选择创意方向不等于确认本母版。", ""]
    for number, (zone, label) in enumerate(ZONES.items(), 1):
        lines.append(str(number) + ". " + label)
        if not master["zones"][zone]:
            lines.append("   本画面无独立补充项。")
        for key in master["zones"][zone]:
            item = master["items"][key]
            status = "已确认" if approved or item["confirmation_status"] == "confirmed" else "待确认"
            lines.append("   - " + display_value(item) + " [" + SOURCES[item["design_source"]] +
                         "；" + status + "；" + STRENGTH[item["constraint_strength"]] + "]")
    lines.append("\n全局属性")
    for label, key in (("媒介", master["globals"]["medium"]), ("画幅", master["globals"]["aspect_ratio"])):
        lines.append("- " + label + "：" + display_value(master["items"][key]))
    if not master["globals"]["image_text"]:
        lines.append("- 画面文字：本版没有可读文字设计。")
    for key in master["globals"]["image_text"]:
        lines.append("- 画面文字：" + display_value(master["items"][key]))
    if master["changes"]:
        lines.append("\n本版变更")
        for change in master["changes"]:
            lines.append("- " + change["operation"] + " " + change["item_id"] + "：" + change["reason"])
    if master.get("structure_changes"):
        lines.append("\n本版结构变更")
        for change in master["structure_changes"]:
            lines.append("- " + change["path"] + "：" + change["reason"])
    lines.append("\n请明确确认此母版版本，或提出局部修改。")
    return "\n".join(lines)

def verify_revision(state, candidate, authorization=None):
    validate_master(candidate)
    if not state["masters"]:
        require(not candidate.get("structure_changes"), "首版以完整结构快照为起点，不填写相对旧版的结构变更")
        require(candidate["revision"] == 1 and candidate["parent_revision"] is None, "首版必须为 v1，父版本为空")
        expected = {(k, "add") for k in candidate["items"]}
        require({(c["item_id"], c["operation"]) for c in candidate["changes"]} == expected, "首版变更须覆盖所有新增项")
        return {"changed": sorted(candidate["items"]), "affected": sorted(candidate["items"])}
    old = latest(state)
    require(candidate["master_id"] == old["master_id"], "任务母版 ID 不得切换")
    require(candidate["revision"] == old["revision"] + 1 and candidate["parent_revision"] == old["revision"], "版本必须递增且关联当前父版本")
    changes = {}
    for key in old["items"].keys() | candidate["items"].keys():
        if key not in old["items"]:
            changes[key] = "add"
        elif key not in candidate["items"]:
            changes[key] = "remove"
        elif old["items"][key] != candidate["items"][key]:
            changes[key] = "update"
    actual = [(c["item_id"], c["operation"]) for c in candidate["changes"]]
    require(len(actual) == len(set(actual)) and set(actual) == set(changes.items()), "变更记录与实际设计项差异不一致")
    structural = {}
    for section in ("zones", "globals"):
        for key in old[section]:
            if old[section][key] != candidate[section][key]:
                structural[section + "." + key] = {"before": old[section][key], "after": candidate[section][key]}
    records = candidate.get("structure_changes", [])
    paths = [record["path"] for record in records]
    require(len(paths) == len(set(paths)) and set(paths) == set(structural), "结构变更记录须准确覆盖实际区域及全局引用变化")
    require(all(record["reason"].strip() and record["source_ref"].strip() for record in records), "结构变更须有具体理由及来源")
    require(changes or structural, "不创建无变化版本")
    allowed = set((authorization or {}).get("item_ids", []))
    for key in changes:
        if key in old["items"] and old["items"][key]["constraint_strength"] in ("hard_constraint", "confirmed_design"):
            require(key in allowed and (authorization or {}).get("user_ref"), "修改锁定项需要明确用户授权: " + key)
    affected = set(impact(old, candidate, changes))
    for change in structural.values():
        for value in (change["before"], change["after"]):
            affected.update(value if type(value) is list else [value])
    old_ratio = old["items"][old["globals"]["aspect_ratio"]]["value"]
    new_ratio = candidate["items"][candidate["globals"]["aspect_ratio"]]["value"]
    if old_ratio["width"] * new_ratio["height"] != new_ratio["width"] * old_ratio["height"]:
        # These areas need host review even when authored dependency edges are incomplete.
        for zone in ("visual_subject_hierarchy", "character_art", "scene_art", "action_spatial_relations", "camera_composition"):
            affected.update(old["zones"][zone])
            affected.update(candidate["zones"][zone])
    return {"changed": sorted(changes), "affected": sorted(affected),
            "structural_changes": [{**record, **structural[record["path"]]} for record in records]}

def is_approved(state, master):
    return any(a["master_hash"] == digest(master) and a["revision"] == master["revision"]
               for a in state["approvals"])

