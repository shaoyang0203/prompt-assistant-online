import sys
from harness import main

if __name__ == "__main__":
    # Keep global --data-dir before the subcommand.
    args = sys.argv[1:]
    init = "--init" in args
    args = [x for x in args if x != "--init"]
    raise SystemExit(main(args + ["check"] + (["--init"] if init else [])))
