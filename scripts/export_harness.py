"""Alias: export_harness.py --data-dir DIR --kind full --output FILE."""
import sys
from harness import main

if __name__ == "__main__":
    args = sys.argv[1:]
    global_args = []
    if "--data-dir" in args:
        i = args.index("--data-dir")
        global_args = args[i:i+2]
        del args[i:i+2]
    raise SystemExit(main(global_args + ["export"] + args))
