"""Command line interface. JSON input files contain data, never executable code."""
import argparse
import json
from pathlib import Path
import sys
import zipfile

from harness_core import (Store, HarnessError, export_data, import_data, read_json,
                          clarify_unexpected, validate_records)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prompt Assistant Online Harness")
    parser.add_argument("--data-dir", help="独立且持久的数据目录；不允许位于 Skill 内")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--init", action="store_true")
    start = sub.add_parser("start")
    start.add_argument("--session", required=True)
    start.add_argument("--init", action="store_true")
    toggle = sub.add_parser("toggle")
    toggle.add_argument("state", choices=("on", "off"))
    for command in ("feedback", "candidate", "experiment", "clarify", "configure"):
        p = sub.add_parser(command)
        p.add_argument("--input", required=True)
    query = sub.add_parser("query")
    query.add_argument("--context", required=True)
    query.add_argument("--model", required=True)
    query.add_argument("--model-version", default="未知")
    query.add_argument("--current-feature", action="append", default=[])
    manage = sub.add_parser("manage")
    manage.add_argument("operation", choices=("learning", "apply", "authorize", "disable", "correct", "forget", "clear"))
    manage.add_argument("--id")
    manage.add_argument("--value", help="on/off 或修正文本")
    manage.add_argument("--confirm", action="store_true")
    rollback = sub.add_parser("rollback")
    rollback.add_argument("--id", required=True)
    rollback.add_argument("--reason", required=True)
    export = sub.add_parser("export")
    export.add_argument("--kind", choices=("preferences", "harness", "full"), default="full")
    export.add_argument("--output", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--input", required=True)
    sub.add_parser("validate")
    sub.add_parser("show")
    args = parser.parse_args(argv)
    try:
        store = Store(args.data_dir)
        if args.command == "check":
            result = store.probe(create=args.init)
        elif args.command == "start":
            result = store.start(args.session, create=args.init)
        elif args.command == "toggle":
            result = store.toggle(args.state == "on")
        elif args.command in ("feedback", "candidate", "experiment"):
            result = getattr(store, args.command)(**read_json(args.input))
        elif args.command == "clarify":
            result = clarify_unexpected(**read_json(args.input))
        elif args.command == "configure":
            result = store.configure(read_json(args.input))
        elif args.command == "query":
            result = store.applicable(args.context, args.model, args.model_version, args.current_feature)
        elif args.command == "manage":
            value = {"on": True, "off": False}.get(args.value, args.value)
            result = store.manage(args.operation, args.id, value, args.confirm)
        elif args.command == "rollback":
            result = store.rollback(args.id, args.reason)
        elif args.command == "export":
            result = export_data(store, args.output, args.kind)
        elif args.command == "import":
            result = import_data(store, args.input)
        else:
            data = store.load()
            validate_records(data)
            result = data if args.command == "show" else {"valid": True, "data_dir": str(store.root)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result is None or result.get("available", True) else 2
    except (OSError, ValueError, KeyError, TypeError, StopIteration, zipfile.BadZipFile) as exc:
        print(json.dumps({"saved": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
