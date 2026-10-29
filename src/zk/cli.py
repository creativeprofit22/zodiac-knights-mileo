"""`zk <stage> [...]`: one subcommand per stage, plus `tools` and `status`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import stages
from .core import toolchain
from .core.codehash import code_hash, stage_sources
from .core.context import Context
from .core.workspace import GAME

RESERVED_NAMES = frozenset({GAME, "status", "tools"})  # manifest key / built-in subcommands


def run_stage(ctx: Context, mod, args) -> dict:
    """Run one stage and record its result, code hash and adapters in the manifest.

    Exceptions from the stage propagate; nothing is recorded then."""
    ctx.used.clear()
    info = mod.execute(ctx, args)
    used = dict(ctx.used)
    info = {**info,
            "code_hash": code_hash(stage_sources((mod.__name__, mod.__file__),
                                                    [(u["module"], u["file"]) for u in used.values()])),
            "adapters": {port: {"adapter": u["adapter"], "module": u["module"]} for port, u in used.items()}}
    ctx.ws.record(mod.NAME, info)
    return info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zk", description=__doc__)
    parser.add_argument("--config", type=Path, help="config file (default: zk.toml at the repo root, or ./zk.toml when installed)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tools", help="download the pinned portable tools into ./tools")
    t.add_argument("names", nargs="*", help="default: all")
    sub.add_parser("status", help="show configured adapters and the workspace manifest")

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
