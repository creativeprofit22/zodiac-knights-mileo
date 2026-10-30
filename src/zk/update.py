"""`zk update`: run every stage in order, skipping the ones whose fingerprint is unchanged.

Modelled on SSA update.py (6e1be49). A step is current when its manifest record has an `update_stamp`
whose fingerprint parts (code closure, adapters, pinned tools, packages, options) and inputs (version,
argv, and digests of what it `uses` from upstream steps) still match, and its outputs exist. So an upstream
rerun cascades only when the files or record values a step consumes changed. A manual `zk <stage>`
rewrites the record without a stamp, so the next update reruns it. Stage knowledge lives in zk.steps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType

from . import stages
from .core.codehash import fingerprint_parts
from .core.context import Context
from .core.runner import run_stage
from .steps import STEPS, Path_, Step

REPORT_KEY = "update"
NO_STAMP = "no stamp (never run by update, or run manually)"
MAX_OUTPUT_REASONS = 3
_ABSENT = object()


def _say(msg: str, *, err: bool = False) -> None:
    print(msg, file=sys.stderr if err else sys.stdout, flush=True)


def fingerprint(parts: dict, inputs: dict, result: dict) -> str:
    blob = json.dumps({"parts": parts, "inputs": inputs, "result": result}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def lookup(record: object, path: Path_) -> object:
    """Follow `path` into a stage record; "*" maps over a dict, "#" counts. Missing -> None."""
    if not path:
        return record
    head, rest = path[0], path[1:]
    if head == "#":
        return len(record) if isinstance(record, (list, dict)) else None
    if not isinstance(record, dict):
        return None
    if head == "*":
        return {k: lookup(v, rest) for k, v in sorted(record.items())}
    return lookup(record.get(head), rest)


def _arrow(old: object, new: object) -> str:
    return f"{'-' if old is None else old}->{'-' if new is None else new}"


def parts_diff(old: dict, new: dict) -> list[str]:
    out = []
    if old.get("code_hash") != new.get("code_hash"):
        out.append("code changed")
    for kind, label in (("adapters", "adapter"), ("packages", "package")):
        o, n = old.get(kind, {}), new.get(kind, {})
        out += [f"{label} {k}: {_arrow(o.get(k), n.get(k))}" for k in sorted({*o, *n}) if o.get(k) != n.get(k)]
    o, n = old.get("tools", {}), new.get("tools", {})
    for k in sorted({*o, *n}):
        if o.get(k) != n.get(k):
            ov, nv = (str(x).split(" ")[0] if x else None for x in (o.get(k), n.get(k)))
            out.append(f"pinned tool {k} " + (_arrow(ov, nv) if ov != nv else "sha256 changed"))
    o, n = old.get("options", {}), new.get("options", {})
    for port in sorted({*o, *n}):
        po, pn = o.get(port, {}), n.get(port, {})
        out += [f"option {port}.{k} changed" for k in sorted({*po, *pn}) if po.get(k) != pn.get(k)]
    return out


def inputs_diff(old: dict, new: dict) -> list[str]:
    out = []
    if old.get("version") != new.get("version"):
        out.append(f"version {_arrow(old.get('version'), new.get('version'))}")
    if old.get("argv") != new.get("argv"):
        out.append(f"argv {_arrow(' '.join(old.get('argv') or []), ' '.join(new.get('argv') or []))}")
    o, n = old.get("consumed") or {}, new.get("consumed") or {}
    for u in sorted({*o, *n}):
        ou, nu = o.get(u) or {}, n.get(u) or {}
        keys: list[str] = []
        for kind in ("files", "trees", "record"):
            ok, nk = ou.get(kind) or {}, nu.get(kind) or {}
            keys += [k for k in sorted({*ok, *nk}) if ok.get(k, _ABSENT) != nk.get(k, _ABSENT)]
        out += [f"{u} output {k} changed" for k in keys[:MAX_OUTPUT_REASONS]]
        if len(keys) > MAX_OUTPUT_REASONS:
            out.append(f"{u} output: +{len(keys) - MAX_OUTPUT_REASONS} more changed")
    return out


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_tree(root: Path) -> str:
    """Size+mtime manifest of every file under `root`; cheap for multi-GB folders."""
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        st = p.stat()
        h.update(f"{p.relative_to(root).as_posix()}\t{st.st_size}\t{st.st_mtime_ns}\n".encode("utf-8"))
    return h.hexdigest()


def duration(seconds: float) -> str:
    return f"{seconds:.0f}s" if seconds < 60 else f"{seconds / 60:.1f} min"


def _show(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list, bool)) or value is None \
        else str(value)


@dataclass
class Decision:
    reasons: list[str]
    inputs: dict
    cache: dict = field(default_factory=dict)  # {rel: [size, mtime_ns, sha256]} of consumed files
    parts: dict | None = None
    legacy: bool = False  # stamp predates consumed digests
    maybe: list[str] = field(default_factory=list)  # pending upstreams that decide it (dry run)


class Updater:
    def __init__(self, ctx: Context, steps: Iterable[Step], modules: dict[str, ModuleType], *,
                 clock: Callable[[], float], now: Callable[[], datetime], prog: str = "zk") -> None:
        self.ctx, self.steps, self.modules = ctx, tuple(steps), modules
        self.clock, self.now, self.prog = clock, now, prog
        self.memo: dict[str, tuple[int, int, str]] = {}  # rel -> (size, mtime_ns, sha256): read once per run
        self.snapshot: dict[str, str | None] = {}  # stamp fingerprints at run start, for legacy stamps
        self.changed: set[str] = set()

    # --- decisions -------------------------------------------------------------------------------------
    def _record(self, name: str) -> dict:
        rec = self.ctx.ws.manifest().get(name)
        return rec if isinstance(rec, dict) else {}

    def _stamp_of(self, step: Step) -> dict:
        stamp = self._record(step.name).get("update_stamp")
        return stamp if isinstance(stamp, dict) else {}

    def _version(self) -> str | None:
        return self.ctx.ws.facts().get("version")

    def _start(self) -> None:
        self.memo, self.snapshot, self.changed = {}, {}, set()
        for step in self.steps:
            stamp = self._stamp_of(step)
            self.snapshot[step.name] = stamp.get("fingerprint")
            for rel, entry in sorted((stamp.get("file_cache") or {}).items()):
                if isinstance(entry, list) and len(entry) == 3:
                    self.memo[rel] = (entry[0], entry[1], entry[2])

    def _glob(self, pattern: str) -> tuple[str, list[Path]]:
        rel = pattern.format(version=self._version())
        return rel, sorted(self.ctx.ws.root.glob(rel))

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.ctx.ws.root).as_posix()

    def _digest(self, path: Path, cache: dict) -> str:
        st, rel = path.stat(), self._rel(path)
        hit = self.memo.get(rel)
        if hit is not None and hit[:2] == (st.st_size, st.st_mtime_ns):
            sha = hit[2]
        else:
            sha = _hash_file(path)
            self.memo[rel] = (st.st_size, st.st_mtime_ns, sha)
        cache[rel] = [st.st_size, st.st_mtime_ns, sha]
        return sha

    def _consumed(self, step: Step) -> tuple[dict, dict]:
        """Digests of everything `step` uses from its upstreams (read-only), plus the file stat cache."""
        consumed: dict = {}
        cache: dict = {}
        for u, uses in step.uses.items():
            files: dict[str, str | None] = {}
            trees: dict[str, str | None] = {}
            for pattern in uses.files:
                rel, found = self._glob(pattern)
                found = [p for p in found if p.is_file()]
                if not found:
                    files[rel] = None
                for p in found:
                    files[self._rel(p)] = self._digest(p, cache)
            for pattern in uses.trees:
                rel, found = self._glob(pattern)
                found = [p for p in found if p.is_dir()]
                if not found:
                    trees[rel] = None
                for p in found:
                    trees[self._rel(p)] = _hash_tree(p)
            rec = self._record(u)
            consumed[u] = {"files": files, "trees": trees,
                           "record": {".".join(path): lookup(rec, path) for path in uses.record}}
        return consumed, cache

    def _missing(self, step: Step) -> list[str]:
        version = self._version()
        rels = [o.format(version=version) for o in step.outputs]
        return [rel for rel in rels if version is None or not (self.ctx.ws.root / rel).exists()]

    def _parts(self, step: Step, ports: Iterable[str]) -> dict:
        return fingerprint_parts(self.modules[step.name], sorted(ports), self.ctx.cfg)

    def decide(self, step: Step, force: bool, busy: set[str]) -> Decision:
        """Reasons to rerun (empty = current). `busy` holds upstreams that ran (or will run, in a plan)."""
        if step.source:
            d = Decision([], {"argv": list(step.argv)})
        else:
            consumed, cache = self._consumed(step)
            d = Decision([], {"version": self._version(), "argv": list(step.argv), "consumed": consumed}, cache)
        stamp = self._stamp_of(step)
        if force:
            d.reasons = ["--force"]
            return d
        if not stamp:
            d.reasons = [NO_STAMP]
            return d
        try:
            d.parts = self._parts(step, stamp["parts"].get("adapters", {}))
            d.reasons = parts_diff(stamp["parts"], d.parts)
        except RuntimeError as e:
            d.reasons = [str(e)]
        old = stamp.get("inputs") or {}
        d.legacy = "consumed" not in old and not step.source
        if d.legacy:
            # adopt an old-format stamp only under the old rule: upstream fingerprints unchanged since it ran
            keys = ("version", "argv")
            d.reasons += inputs_diff({k: old.get(k) for k in keys}, {k: d.inputs[k] for k in keys})
            upstream = old.get("upstream") or {}
            # upstreams the old stamp didn't record were covered transitively by the ones it did
            d.reasons += [f"upstream {u} changed" for u in step.after
                          if (u in upstream and upstream[u] != self.snapshot.get(u)) or u in busy]
        else:
            d.reasons += inputs_diff(old, d.inputs)
        d.reasons += [f"missing {rel}" for rel in self._missing(step)]
        if not d.reasons and not d.legacy:
            d.maybe = [u for u in step.after if u in busy]
        return d

    def _timing(self, step: Step) -> str:
        stamp = self._stamp_of(step)
        if "seconds" in stamp:
            return f"last {duration(stamp['seconds'])}"
        return f"est. {step.estimate}" if step.estimate else "est. unknown"

    def plan(self, start: int, force: bool) -> list[str]:
        """Plan lines, assuming the device source is unchanged; writes nothing."""
        lines: list[str] = []
        pending: set[str] = set()
        for i, step in enumerate(self.steps):
            if i < start:
                decision, reason = "keep", "before --from"
            elif step.source:
                decision, reason = "check", "checks the device source" + (" (--force)" if force else "")
            else:
                d = self.decide(step, force, pending)
                if d.reasons:
                    decision, reason = "run", "; ".join(d.reasons)
                elif d.maybe:
                    decision, reason = "maybe", f"reruns if {' or '.join(d.maybe)} output changes"
                else:
                    decision, reason = "skip", "unchanged"
                if decision != "skip":
                    pending.add(step.name)
            lines.append(f"  {step.name:<8} {decision:<5} {self._timing(step):<40} {reason}")
        return lines

    # --- running ---------------------------------------------------------------------------------------
    def _execute(self, step: Step, argv: list[str]) -> dict:
        mod = self.modules[step.name]
        parser = argparse.ArgumentParser(prog=f"{self.prog} {step.name}")
        if hasattr(mod, "add_arguments"):
            mod.add_arguments(parser)
        return run_stage(self.ctx, mod, parser.parse_args(argv))

    def _stamp(self, step: Step, d: Decision, seconds: float) -> None:
        rec = self._record(step.name)
        parts = self._parts(step, rec.get("adapters", {}))
        result = {k: rec.get(k) for k in step.fingerprint_keys}
        stamp = {"fingerprint": fingerprint(parts, d.inputs, result), "parts": parts, "inputs": d.inputs,
                 "result": result, "seconds": seconds, "at": self.now().isoformat(timespec="seconds")}
        if d.cache:
            stamp["file_cache"] = d.cache
        rec["update_stamp"] = stamp
        self.ctx.ws.record(step.name, rec)

    def _refresh(self, step: Step, d: Decision) -> None:
        """After a skip, rewrite the stamp only if it is old-format or its file cache moved."""
        rec = self._record(step.name)
        stamp = rec.get("update_stamp") or {}
        if d.parts is None or not (d.legacy or (stamp.get("file_cache") or {}) != d.cache):
            return
        stamp = {k: v for k, v in stamp.items() if k != "file_cache"}
        stamp.update(fingerprint=fingerprint(stamp.get("parts") or {}, d.inputs, stamp.get("result") or {}),
                     inputs=d.inputs)
        if d.cache:
            stamp["file_cache"] = d.cache
        rec["update_stamp"] = stamp
        self.ctx.ws.record(step.name, rec)

    def _drop_stamp(self, step: Step) -> None:
        rec = self._record(step.name)
        if rec.pop("update_stamp", None) is not None:
            self.ctx.ws.record(step.name, rec)

    def _row(self, step: Step, status: str, reason: str, seconds: float | None = None) -> dict:
        rec = self._record(step.name) if status in ("ran", "skipped") else {}
        counts = {label: lookup(rec, path) for label, path in step.report.items()} if rec else {}
        return {"step": step.name, "status": status, "reason": reason, "seconds": seconds, "counts": counts}

    def run(self, start: str | None = None, force: bool = False, dry_run: bool = False) -> int:
        names = [s.name for s in self.steps]
        first = names.index(start) if start else 0
        self._start()
        _say(f"[update] plan{' (dry run)' if dry_run else ''}:")
        for line in self.plan(first, force):
            _say(line)
        if dry_run:
            return 0

        started, t0 = self.now().isoformat(timespec="seconds"), self.clock()
        rows: list[dict] = []
        failed = False
        for i, step in enumerate(self.steps):
            stamp = self._stamp_of(step)
            if failed or i < first:
                rows.append(self._row(step, "not run", "earlier step failed" if failed else f"--from {start}"))
                continue
            if step.source:
                d = Decision([], {"argv": list(step.argv)})
                argv = [*step.argv, *(step.force_argv if force else ())]
            else:
                d = self.decide(step, force, self.changed)
                if not d.reasons:
                    self._refresh(step, d)
                    _say(f"[update] {step.name}: skipped (unchanged)")
                    rows.append(self._row(step, "skipped", "unchanged"))
                    continue
                argv = [*step.argv, *(step.force_argv if force or stamp else ())]
            reasons = d.reasons
            _say(f"[update] {step.name}: running `{self.prog} {' '.join([step.name, *argv])}`"
                 + (f" ({'; '.join(reasons)})" if reasons else ""))
            t = self.clock()
            try:
                self._execute(step, argv)
            except Exception as e:  # any stage failure stops the run with a hint, never a traceback
                seconds = round(self.clock() - t, 1)
                self._drop_stamp(step)
                rerun = " ".join([self.prog, step.name, *argv])
                _say(f"[update] {step.name} failed: {e}\n  rerun:  {rerun}\n"
                     f"  resume: {self.prog} update --from {step.name}", err=True)
                rows.append(self._row(step, "failed", f"{type(e).__name__}: {e}", seconds))
                failed = True
                continue
            seconds = round(self.clock() - t, 1)
            self._stamp(step, d, seconds)
            changes = self._source_changes(stamp, step) if step.source else reasons
            if changes:
                self.changed.add(step.name)
            if step.source and not changes:
                rows.append(self._row(step, "skipped", "source unchanged", seconds))
            else:
                rows.append(self._row(step, "ran", "; ".join(changes), seconds))

        report = self._report(rows, started, round(self.clock() - t0, 1))
        self.ctx.ws.record(REPORT_KEY, report)
        _say(render(report))
        return 2 if failed else 0

    def _source_changes(self, old_stamp: dict, step: Step) -> list[str]:
        if not old_stamp:
            return [NO_STAMP]
        new = self._stamp_of(step)
        out = parts_diff(old_stamp.get("parts", {}), new.get("parts", {}))
        out += inputs_diff(old_stamp.get("inputs", {}), new.get("inputs", {}))
        prev = old_stamp.get("result", {})
        rec = self._record(step.name)
        for k in step.fingerprint_keys:
            if prev.get(k) != rec.get(k):
                scalar = not isinstance(rec.get(k), (dict, list))
                out.append(f"{k} {_arrow(prev.get(k), rec.get(k))}" if scalar else f"{k} changed")
        return out

    def _report(self, rows: list[dict], started: str, seconds: float) -> dict:
        checks: dict[str, object] = {}
        warnings: list[str] = []
        for step, row in zip(self.steps, rows):
            if row["status"] not in ("ran", "skipped"):
                continue
            rec = self._record(step.name)
            checks.update({label: lookup(rec, path) for label, path in step.checks.items()})
            for path in step.warnings:
                found = lookup(rec, path)
                warnings += [f"{step.name}: {w}" for w in (found if isinstance(found, list) else [])]
        totals = {s: sum(r["status"] == s for r in rows) for s in ("ran", "skipped", "failed", "not run")}
        return {"version": self._version(), "started": started, "seconds": seconds, "totals": totals,
                "steps": rows, "checks": checks, "warnings": warnings}


def render(report: dict) -> str:
    t = report["totals"]
    lines = [f"[update] report for {report['version']} (started {report['started']}, "
             f"{duration(report['seconds'])}): {t['ran']} ran, {t['skipped']} skipped, {t['failed']} failed, "
             f"{t['not run']} not run"]
    for row in report["steps"]:
        secs = "-" if row["seconds"] is None else duration(row["seconds"])
        lines.append(f"  {row['step']:<8} {row['status']:<8} {secs:>8}  {row['reason']}")
        if row["counts"]:
            lines.append("      " + "; ".join(f"{k}: {_show(v)}" for k, v in row["counts"].items()))
    if report["checks"]:
        lines.append("  checks:")
        lines += [f"    {k}: {_show(v)}" for k, v in report["checks"].items()]
    lines.append("  warnings:" + ("" if report["warnings"] else " none"))
    lines += [f"    - {w}" for w in report["warnings"]]
    return "\n".join(lines)


def main(ctx: Context, start: str | None = None, force: bool = False, dry_run: bool = False, *,
         prog: str = "zk", steps: Iterable[Step] = STEPS, clock: Callable[[], float] = time.monotonic,
         now: Callable[[], datetime] = datetime.now) -> int:
    steps = tuple(steps)
    modules = {m.NAME: m for m in stages.load_all(tuple(s.name for s in steps))}
    return Updater(ctx, steps, modules, clock=clock, now=now, prog=prog).run(start, force, dry_run)
