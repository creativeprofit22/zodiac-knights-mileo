"""Compare two csharp_dump summaries per assembly; tag each difference by whether MonoBehaviours use the class.

`compare` is the plain per-assembly diff the code stage records. `tag_used` adds, per assembly, which differing classes
are used (in the MonoBehaviour class set), which match a known counting rule, and what stays unexplained.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping


def _pair(a: int | None, b: int | None) -> list[int | None]:
    return [a, b]


def compare(a: dict, b: dict, assemblies: Iterable[str]) -> dict:
    """Compare two summary.json documents for the given assemblies; a missing side counts as None."""
    report: dict[str, dict] = {}
    mismatches: list[str] = []
    for name in sorted(assemblies):
        sa = a.get("assemblies", {}).get(name)
        sb = b.get("assemblies", {}).get(name)
        ca = sa["classes"] if sa else {}
        cb = sb["classes"] if sb else {}
        gaps = {cls: _pair(ca.get(cls), cb.get(cls)) for cls in sorted(set(ca) | set(cb))
                if ca.get(cls) != cb.get(cls)}
        types = _pair(sa["types"] if sa else None, sb["types"] if sb else None)
        if types[0] != types[1]:
            mismatches.append(name)
        report[name] = {"types": types, "methods": _pair(sa["methods"] if sa else None,
                                                         sb["methods"] if sb else None),
                        "method_gaps": gaps}
    return {"assemblies": report, "type_mismatches": mismatches, "types_match": not mismatches}


def _rule(cls: str, rules: Mapping[str, str]) -> str | None:
    return next((why for pattern, why in sorted(rules.items()) if re.fullmatch(pattern, cls)), None)


def tag_used(diff: dict, used: Mapping[str, Iterable[str]], rules: Mapping[str, str] | None = None) -> dict:
    """Tag `compare` output: used = {assembly: class names MonoBehaviours use}; rules = {class regex: explanation}.

    Unexplained: a used class that differs with no rule, or a type-count gap not accounted for by one-sided classes.
    """
    rules = rules or {}
    out: dict[str, dict] = {}
    total = 0
    for name, r in sorted(diff["assemblies"].items()):
        mine = set(used.get(name, ()))
        gaps: dict[str, dict] = {}
        unexplained: list[str] = []
        only = [0, 0]
        for cls, counts in sorted(r["method_gaps"].items()):
            rule = _rule(cls, rules)
            gaps[cls] = {"counts": counts, "used": cls in mine, "rule": rule}
            if counts[1] is None:
                only[0] += 1
            elif counts[0] is None:
                only[1] += 1
            if cls in mine and rule is None:
                unexplained.append(cls)
        t = r["types"]
        residual = (t[0] - only[0]) - (t[1] - only[1]) if None not in t else 0
        if residual:
            unexplained.append(f"<type count residual {residual}>")
        total += len(unexplained)
        out[name] = {"types": t, "methods": r["methods"], "differences": gaps,
                     "used_classes": len(mine), "type_count_residual": residual, "unexplained": unexplained}
    return {"assemblies": out, "unexplained": total}
