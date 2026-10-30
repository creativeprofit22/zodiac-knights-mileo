"""Run one stage and record what it produced; shared by `zk <stage>` and `zk update`."""
from __future__ import annotations

from types import ModuleType

from .codehash import code_hash, stage_sources
from .context import Context


def run_stage(ctx: Context, mod: ModuleType, args: object) -> dict:
    """Run one stage and record its result, code hash and adapters in the manifest.

    The record replaces the previous one, so a manual run drops any `update_stamp`.
    Exceptions from the stage propagate; nothing is recorded then."""
    ctx.used.clear()
    info = mod.execute(ctx, args)
    used = dict(ctx.used)
    info = {**info,
            "code_hash": code_hash(stage_sources((mod.__name__, mod.__file__ or ""),
                                                    [(u["module"], u["file"]) for u in used.values()])),
            "adapters": {port: {"adapter": u["adapter"], "module": u["module"]} for port, u in used.items()}}
    ctx.ws.record(mod.NAME, info)
    return info
