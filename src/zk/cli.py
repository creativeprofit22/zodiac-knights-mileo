"""`zk <stage> [...]`: one subcommand per stage, plus `update`, `tools` and `status`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import stages, update
from .core import toolchain
from .core.context import Context
from .core.runner import run_stage
from .core.workspace import GAME

__all__ = ["main", "run_stage"]

RESERVED_NAMES = frozenset({GAME, update.REPORT_KEY, "status", "tools"})  # manifest keys / built-in subcommands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zk", description=__doc__)
    parser.add_argument("--config", type=Path, help="config file (default: zk.toml at the repo root, or ./zk.toml when installed)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tools", help="download the pinned portable tools into ./tools")
    t.add_argument("names", nargs="*", help="default: all")
    sub.add_parser("status", help="show configured adapters and the workspace manifest")
    u = sub.add_parser("update", help="run every stage in order, skipping the ones that are current")
    u.add_argument("--from", dest="start", choices=[s.name for s in update.STEPS],
                   help="start at this step; earlier steps are not run")
    u.add_argument("--force", action="store_true", help="rerun every step with its --force flags")
    u.add_argument("--dry-run", action="store_true", help="only print the plan; write nothing, ask no device")

    modules = {}
    for mod in stages.load_all():
        if mod.NAME in RESERVED_NAMES or mod.NAME in modules:
            kind = "reserved" if mod.NAME in RESERVED_NAMES else "duplicate"
            print(f"[zk] stage name {mod.NAME!r} is {kind} (module {mod.__name__}); "
                  f"reserved: {', '.join(sorted(RESERVED_NAMES))}", file=sys.stderr)
            return 2
        p = sub.add_parser(mod.NAME, help=mod.HELP)
        if hasattr(mod, "add_arguments"):
            mod.add_arguments(p)
        modules[mod.NAME] = mod

    args = parser.parse_args(argv)
    try:
        ctx = Context.create(args.config)
    except RuntimeError as e:
        print(f"[zk] config error: {e}", file=sys.stderr)
        return 2

    if args.cmd == "tools":
        for name in args.names or toolchain.TOOLS:
            if name not in toolchain.TOOLS:
                print(f"[tools] unknown tool: {name}", file=sys.stderr)
                return 2
            try:
                print(name, "->", toolchain.path_of(name, ctx.cfg.tools))
            except RuntimeError as e:
                print(f"[tools] error: {e}", file=sys.stderr)
                return 2
        return 0
    if args.cmd == "status":
        print(json.dumps({"adapters": ctx.cfg.adapters, "manifest": ctx.ws.manifest()}, indent=2))
        return 0

    if args.cmd == "update":
        prog = f"zk --config {args.config}" if args.config else "zk"
        return update.main(ctx, args.start, args.force, args.dry_run, prog=prog)

    mod = modules[args.cmd]
    try:
        info = run_stage(ctx, mod, args)
    except RuntimeError as e:
        print(f"[{mod.NAME}] error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(info, indent=2, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
