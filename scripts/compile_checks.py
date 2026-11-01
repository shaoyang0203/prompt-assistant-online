"""Deterministic gate; LLM review is an explicit, hash-bound attestation."""
from contracts import COMPILED_KINDS, VERSION, digest, require
from master import is_approved, latest
import adapter

AXES = ("omissions", "additions", "relations", "requirements")

def prepare(state, target=None):
    master = latest(state)
    require(is_approved(state, master), "拒绝编译：用户尚未确认当前母版版本")
    require(state["coordination"]["status"] == "pass", "拒绝编译：整体协调尚未通过")
    selected = adapter.route(state.get("compilation_target", "generic") if target is None else target)
    adapter.validate_ratio(selected, master["items"][master["globals"]["aspect_ratio"]]["value"])
    require(state["attempts"].get(str(master["revision"]), 0) < 1 + state["limits"]["max_integrity_retries"],
            "编译重试预算已耗尽，请报告问题；不得降低要求")
    facts = {key: item for key, item in master["items"].items() if item["kind"] in COMPILED_KINDS}
    constraints = {key: item for key, item in master["items"].items() if item["kind"] == "constraint"}
    manifest = {"master_id": master["master_id"], "revision": master["revision"],
                "master_hash": digest(master), "adapter_id": selected["id"],
                "aspect_ratio_delivery": selected,
                "facts": facts, "constraints": constraints, "version": VERSION}
    return {"manifest": manifest, "manifest_hash": digest(manifest),
            "host_instruction": "LLM 从本清单编译自然语言 segments；比例只填 parameters.aspect_ratio，不在segments预写画幅控制。"
            "target按本次已选路由填写（省略只表示generic），Adapter依据aspect_ratio_delivery决定最终块内/块外位置。"
            "最终逐项复核并填写独立 review；四个语义轴不能用覆盖 ID 代替。不得补充视觉事实。"}

def body(candidate):
    return adapter.render(candidate)["prompt"]

def review_hash(candidate):
    value = {"segments": candidate["segments"], "parameters": candidate["parameters"]}
    if "target" in candidate:
        value.update({"target": candidate["target"], "route": adapter.route(candidate["target"]),
                      "delivery": adapter.render(candidate)})
    return digest(value)

def inspect(state, candidate, review):
    required = {"master_hash", "segments", "parameters"}
    require(type(candidate) is dict and set(candidate) in (required, required | {"target"}), "成品字段错误")
    packet = prepare(state, candidate.get("target", "generic"))
    manifest = packet["manifest"]
    if "compilation_target" in state:
        require(adapter.route(state["compilation_target"])["id"] == manifest["adapter_id"],
                "成品目标与本次已选路由不同，不能回落通用或其他模型排版")
    problems = []
    require(candidate["master_hash"] == manifest["master_hash"], "成品母版版本过期")
    require(type(candidate["segments"]) is list and bool(candidate["segments"]), "成品段落为空")
    covered = set()
    for segment in candidate["segments"]:
        require(type(segment) is dict and set(segment) == {"text", "item_ids"}, "段落字段错误")
        require(type(segment["text"]) is str and bool(segment["text"].strip()), "段落文本为空")
        require(type(segment["item_ids"]) is list and bool(segment["item_ids"]), "段落缺少覆盖引用")
        require(all(type(x) is str for x in segment["item_ids"]), "覆盖引用类型错误")
        covered.update(segment["item_ids"])
    expected = set(manifest["facts"])
    ratio_id = latest(state)["globals"]["aspect_ratio"]
    is_layout = manifest["aspect_ratio_delivery"]["prompt"] == "json-layout"
    parameter_keys = {"aspect_ratio", "image_size"} if is_layout else {"aspect_ratio"}
    require(type(candidate["parameters"]) is dict and set(candidate["parameters"]) == parameter_keys, "参数字段错误")
    if candidate["parameters"]["aspect_ratio"] != manifest["facts"][ratio_id]["value"]:
        problems.append("画幅与母版不同")
    adapter.ratio_text(candidate["parameters"]["aspect_ratio"])
    problems += adapter.control_problems(candidate, [item["value"]["literal"] for item in manifest["facts"].values()
                                                     if item["kind"] == "image_text"])
    covered.add(ratio_id)
    if expected - covered:
        problems.append("遗漏设计事实: " + ",".join(sorted(expected - covered)))
    if covered - expected:
        problems.append("未知或不可编译设计项: " + ",".join(sorted(covered - expected)))
    if is_layout:
        from moss_layout import visible_texts
        rendered_texts = visible_texts(candidate)
    else:
        rendered_texts = [body(candidate)]
    for key, item in manifest["facts"].items():
        if item["kind"] == "image_text" and not any(item["value"]["literal"] in text for text in rendered_texts):
            problems.append("画面文字未逐字保留: " + key)
    require(type(review) is dict and set(review) == {"master_hash", "artifact_hash", "reviewer", "evidence_ref", "axes", "item_results"}, "语义复核字段错误")
    require(review["master_hash"] == manifest["master_hash"] and review["artifact_hash"] == review_hash(candidate), "语义复核与成品或母版不匹配")
    require(type(review["reviewer"]) is str and bool(review["reviewer"].strip()) and
            type(review["evidence_ref"]) is str and bool(review["evidence_ref"].strip()), "缺少语义复核来源")
    require(type(review["axes"]) is dict and set(review["axes"]) == set(AXES), "语义复核轴不完整")
    require(type(review["item_results"]) is dict and set(review["item_results"]) == expected, "逐项语义复核范围不完整")
    results = []
    for value in list(review["axes"].values()) + list(review["item_results"].values()):
        require(type(value) is dict and set(value) == {"result", "note"}, "语义复核结论结构错误")
        require(value["result"] in ("pass", "fail", "uncertain") and type(value["note"]) is str and bool(value["note"].strip()), "语义复核结论无效")
        results.append(value["result"])
    semantic = "fail" if "fail" in results else "uncertain" if "uncertain" in results else "pass"
    result = "fail" if problems or semantic == "fail" else semantic
    return {"result": result, "structural": "fail" if problems else "pass", "semantic": semantic,
            "problems": problems, "assurance_mode": "python-plus-host-llm-attestation",
            "limitation": "Python 不证明自然语言等义；语义结果来自所提供的 LLM 复核声明，非独立模型验证。"}

