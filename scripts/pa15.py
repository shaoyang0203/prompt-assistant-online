#!/usr/bin/env python3
"""PA15 preview local tool. The host LLM performs all free-input creative work."""
import argparse
import json
import sys
from uuid import uuid4
sys.dont_write_bytecode = True
from contracts import ContractError, read_json, validate_master
from harness_store import Store
import flow
from compile_checks import prepare
from master import render
from preview_cases import CORRECTION, build, candidate_for, authored_review

def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description="V1.5.0-harness（非自动生图程序）")
    parser.add_argument("--data-dir", help="源码之外的本地运行数据目录")
    parser.add_argument("--task", default="session")
    sub = parser.add_subparsers(dest="command", required=True)
    p=sub.add_parser("new"); p.add_argument("--request",required=True); p.add_argument("--limits")
    p=sub.add_parser("concepts"); p.add_argument("--input",required=True)
    p=sub.add_parser("select"); p.add_argument("--concept",required=True); p.add_argument("--user-ref",required=True)
    p=sub.add_parser("master"); p.add_argument("--input",required=True); p.add_argument("--authorization")
    p=sub.add_parser("change"); p.add_argument("--user-ref",required=True)
    p=sub.add_parser("coordinate"); p.add_argument("--input",required=True)
    sub.add_parser("show")
    p=sub.add_parser("approve"); p.add_argument("--revision",type=int,required=True); p.add_argument("--user-ref",required=True)
    p=sub.add_parser("manifest"); p.add_argument("--target", help="已登记目标路由；省略沿用本任务选择，初次为generic")
    p=sub.add_parser("submit"); p.add_argument("--candidate",required=True); p.add_argument("--review",required=True)
    sub.add_parser("deliver"); sub.add_parser("status")
    p=sub.add_parser("correction"); p.add_argument("--input",required=True)
    p=sub.add_parser("validate"); p.add_argument("--input",required=True)
    p=sub.add_parser("preview"); p.add_argument("--case",choices=["portrait","environment","correction"],default="portrait")
    args=parser.parse_args()
    if args.command=="validate":
        validate_master(read_json(args.input))
        return {"result":"pass","scope":"V1.5.0 Schema 子集及业务约束；未证明视觉质量"},0
    if not args.data_dir:
        parser.error("本地记录操作需要明确 --data-dir；核心 Skill 文本创作不需要 Python")
    store=Store(args.data_dir)
    command=args.command
    if command=="preview":
        return preview(store,args.case),0
    if command=="new":
        limits=read_json(args.limits) if args.limits else None
        return store.create(args.task,flow.new_task(args.task,args.request,limits)),0
    actions={
      "concepts":lambda s:flow.set_concepts(s,read_json(args.input)),
      "select":lambda s:flow.select(s,args.concept,args.user_ref),
      "master":lambda s:flow.save_master(s,read_json(args.input),read_json(args.authorization) if args.authorization else None),
      "change":lambda s:flow.begin_change(s,args.user_ref),
      "coordinate":lambda s:flow.coordinate(s,**read_json(args.input)),
      "show":flow.show,
      "approve":lambda s:flow.approve(s,args.revision,args.user_ref),
      "manifest":lambda s:flow.prepare_manifest(s,args.target),
      "submit":lambda s:flow.submit(s,read_json(args.candidate),read_json(args.review)),
      "correction":lambda s:flow.correction(s,read_json(args.input))
    }
    if command in actions:
        result=store.update(args.task,actions[command])
    else:
        state=store.load(args.task)
        result=flow.deliver(state) if command=="deliver" else state
    return result, 1 if result.get("result") in ("fail","uncertain") else 0

def preview(store,case):
    print("预写合成示例体验；不是任意输入生成器，不调用生图模型。")
    task="preview-"+case+"-"+uuid4().hex[:8]
    data=build(case)
    store.create(task,flow.new_task(task,data["request"]))
    if case=="correction":
        store.update(task,lambda s:flow.correction(s,CORRECTION))
        print(json.dumps(CORRECTION,ensure_ascii=False,indent=2))
        if input("是否选择局部调整，允许放宽为全身景别？输入 是，其他输入退出：").strip()!="是":
            return {"saved":True,"task_id":task,"status":"等待纠偏选择"}
    store.update(task,lambda s:flow.set_concepts(s,data["concepts"]))
    for c in data["concepts"]:
        print("\n"+c["id"]+" "+c["core"]+"\n视觉重点："+c["focus"]+"\n特色："+c["feature"]+"\n"+c["scene"])
    selected=input("\n选择 A/B/C，其他输入退出：").strip().upper()
    if selected not in ("A","B","C"):
        return {"saved":True,"task_id":task,"status":"等待方向选择"}
    data=build(case,ord(selected)-ord("A"))
    store.update(task,lambda s:flow.select(s,selected,"interactive:user-direction"))
    store.update(task,lambda s:flow.save_master(s,data["master"]))
    store.update(task,lambda s:flow.coordinate(s,"pass",[],"示例作者已对照空间、光色、可见性；本次不是独立模型评价",
                       ["scene_art","camera_composition","lighting_color"]))
    shown=store.update(task,flow.show)
    print("\n"+shown["text"])
    if input("\n确认此母版 v1 后才编译。输入 确认v1，其他输入保持待确认：").strip()!="确认v1":
        return {"saved":True,"task_id":task,"status":"母版未确认，未编译"}
    store.update(task,lambda s:flow.approve(s,1,"interactive:user-confirmed-v1"))
    state=store.load(task)
    candidate=candidate_for(state,data["translations"])
    review=authored_review(state,candidate)
    report=store.update(task,lambda s:flow.submit(s,candidate,review))
    if report["result"]!="pass":
        return report
    output=flow.deliver(store.load(task))
    print("\n"+output["formatted"])
    return {"saved":True,"task_id":task,"status":"示例闭环完成","evidence":"作者预写复核，非独立在线 LLM 测试；未实际出图"}

if __name__=="__main__":
    try:
        result,code=main()
        print(json.dumps(result,ensure_ascii=False,indent=2))
        raise SystemExit(code)
    except (ContractError,OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({"saved":False,"error":str(exc)},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)

