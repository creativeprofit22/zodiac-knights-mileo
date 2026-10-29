"""Summaries of decompiled C# projects: types, methods and body kinds per assembly (report.json).

Input: {"<Asm>/<path>.cs": source}. The first path part names the assembly. Shape per assembly:
{"types": n, "methods": n, "bodies": {"none": n, "reconstructed": n, "stub": n}}.
Types: class/struct/interface/enum/record/delegate declarations, nested included. Methods: methods, constructors,
operators and property/indexer/event accessors. A body is a "stub" when it is empty or only holds a placeholder
(STUB_STATEMENTS / STUB_EXPRESSION: throw, default returns, out-defaults, this-forwarders), "none" when there is
no body (abstract, extern, interface members, auto and `field` accessors), and "reconstructed" otherwise.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TypedDict

DISCLAIMER = ("Reconstructed from IL2CPP metadata. This is not the original C#: names and signatures come from "
              "metadata, and method bodies are stubs or best-effort. The Ghidra stage is the source of truth for logic.")

_CLEAN = re.compile(
    r'//[^\n]*'                          # line comment
    r'|/\*.*?\*/'                        # block comment
    r'|""".*?"""'                        # raw string
    r'|[$@]{1,2}"(?:[^"]|"")*"'          # verbatim / interpolated string
    r'|"(?:[^"\\\n]|\\.)*"'              # string
    r"|'(?:[^'\\\n]|\\.)+'"              # char
    r'|^[ \t]*#[^\n]*',                  # preprocessor line
    re.S | re.M)
_KIND = re.compile(r"(?:^|\s)(class|struct|interface|enum|record)(?:\s+(?:class|struct))?\s+@?\w")
_DELEGATE = re.compile(r"(?:^|\s)delegate\s")
_NAMESPACE = re.compile(r"^namespace\s")
_ASSIGN = re.compile(r"(?<![=!<>])=(?![=>])")
# Cpp2IL dummydll bodies (seen on this game): `return null|false|0|0f|0L|0u|0.0|default;`, optionally after
# `out` parameters set to null/default; ILSpy adds one-line `this.X(args)` forwarders for .override methods.
_DEFAULT = r"(?:null|false|default(?:\s*\([^;]*\))?|0(?:\.0+)?[fFdDmMuUlL]{0,2})"
_THROW = r"throw\s+null|throw\s+new\s+(?:System\.)?NotImplementedException\s*\([^;]*\)"
_FORWARD = r"(?:return\s+)?this\.\w+\(\s*(?:\w+(?:\s*,\s*\w+)*)?\s*\)"
_PLACEHOLDER = rf"{_THROW}|{_DEFAULT}|{_FORWARD}"
STUB_STATEMENTS = re.compile(rf"^(?:[\w.]+\s*=\s*{_DEFAULT}\s*;\s*)*"
                             rf"(?:(?:{_THROW}|return\s+{_DEFAULT}|{_FORWARD})\s*;)?$")
STUB_EXPRESSION = re.compile(rf"^(?:{_PLACEHOLDER})$")
# C# 14 `field` accessors carry no logic, like auto accessors.
AUTO_ACCESSOR = re.compile(r"^(?:return\s+field\s*;|field\s*=\s*value\s*;|field)$")


class Bodies(TypedDict):
    none: int
    reconstructed: int
    stub: int


class AssemblyReport(TypedDict):
    types: int
    methods: int
    bodies: Bodies


def _clean(text: str) -> str:
    """Drop comments and preprocessor lines; turn literals into "" so their braces do not count."""
    def repl(m: re.Match[str]) -> str:
        return '""' if m.group(0)[:1] in "\"$@'" else " "
    return _CLEAN.sub(repl, text.replace("\r\n", "\n"))


def _match(text: str, i: int) -> int:
    """Index of the `}` closing the `{` at i (end of text when unbalanced)."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(text) - 1


def _strip_attributes(header: str) -> str:
    header = header.strip()
    while header.startswith("["):
        depth = 0
        for j, ch in enumerate(header):
            depth += ch == "["
            depth -= ch == "]"
            if depth == 0:
                header = header[j + 1:].strip()
                break
        else:
            return ""
    return header


def _top(header: str) -> str:
    """The header with everything inside (), [] and <> blanked, so only top-level tokens stay."""
    out: list[str] = []
    depth = 0
    for ch in header:
        if ch in "([<":
            depth += 1
            out.append(ch if depth == 1 else " ")
        elif ch in ")]>" and depth:
            out.append(ch if depth == 1 else " ")
            depth -= 1
        else:
            out.append(ch if depth == 0 else " ")
    return "".join(out)


def _head(top: str) -> str:
    """Declaration part before parameters and generic constraints."""
    return re.split(r"\bwhere\b", top.split("(", 1)[0], maxsplit=1)[0]


class _Counter:
    def __init__(self) -> None:
        self.types = 0
        self.methods = 0
        self.bodies = {"none": 0, "reconstructed": 0, "stub": 0}

    def method(self, body: str | None, expression: bool = False) -> None:
        self.methods += 1
        if body is None:
            self.bodies["none"] += 1
            return
        text = " ".join(body.split())
        if AUTO_ACCESSOR.match(text):
            self.bodies["none"] += 1
            return
        stub = (STUB_EXPRESSION if expression else STUB_STATEMENTS).match(text)
        self.bodies["stub" if stub else "reconstructed"] += 1

    def statement(self, raw: str, container: str) -> None:
        h = _strip_attributes(raw)
        if not h or h.startswith("using ") or _NAMESPACE.match(h):
            return
        top = _top(h)
        if _DELEGATE.search(_head(top)) or (container != "accessors" and _KIND.search(_head(top))):
            self.types += 1  # delegate or positional record
            return
        arrow = top.find("=>")
        if container == "accessors":
            self.method(h[arrow + 2:].strip() if arrow >= 0 else None, expression=True)
            return
        if container not in ("type", "interface"):
            return
        paren, assign = top.find("("), _ASSIGN.search(top)
        first = min([p for p in (arrow, assign.start() if assign else -1) if p >= 0], default=len(top))
        if 0 <= paren < first:  # method without a block body
            self.method(h[arrow + 2:].strip() if arrow >= 0 else None, expression=True)
        elif arrow >= 0 and arrow == first:  # expression-bodied property
            self.method(h[arrow + 2:].strip(), expression=True)

    def scan(self, text: str, i: int, container: str) -> int:
        """Read members from i up to the `}` closing this container; return the index after it."""
        start = i
        while i < len(text):
            ch = text[i]
            if ch == "}":
                return i + 1
            if ch == ";":
                self.statement(text[start:i], container)
                start = i = i + 1
                continue
            if ch != "{":
                i += 1
                continue
            h = _strip_attributes(text[start:i])
            top = _top(h)
            end = _match(text, i)
            if "=>" in top or _ASSIGN.search(top):  # initializer or expression braces: the member ends at `;`
                i = end + 1
                continue
            kind = _KIND.search(_head(top)) if container != "accessors" else None
            if _NAMESPACE.match(h):
                i = self.scan(text, i + 1, "namespace")
            elif kind:
                self.types += 1
                i = end + 1 if kind.group(1) == "enum" else self.scan(
                    text, i + 1, "interface" if kind.group(1) == "interface" else "type")
            elif container == "accessors" or "(" in top:
                self.method(text[i + 1:end])
                i = end + 1
            elif container in ("type", "interface"):
                i = self.scan(text, i + 1, "accessors")
            else:
                i = end + 1
            start = i
        return i


def summarize_source(text: str) -> AssemblyReport:
    c = _Counter()
    c.scan(_clean(text), 0, "top")
    b = c.bodies
    return {"types": c.types, "methods": c.methods,
            "bodies": {"none": b["none"], "reconstructed": b["reconstructed"], "stub": b["stub"]}}


def summarize(files: Mapping[str, str]) -> dict[str, AssemblyReport]:
    """Per-assembly counts over "<Asm>/<path>.cs" sources; keys sorted."""
    out: dict[str, AssemblyReport] = {}
    for path in sorted(files):
        norm = path.replace("\\", "/")
        if not norm.lower().endswith(".cs") or "/" not in norm:
            continue
        s = summarize_source(files[path])
        acc = out.setdefault(norm.split("/", 1)[0],
                             {"types": 0, "methods": 0, "bodies": {"none": 0, "reconstructed": 0, "stub": 0}})
        acc["types"] += s["types"]
        acc["methods"] += s["methods"]
        acc["bodies"]["none"] += s["bodies"]["none"]
        acc["bodies"]["reconstructed"] += s["bodies"]["reconstructed"]
        acc["bodies"]["stub"] += s["bodies"]["stub"]
    return out


def report(assemblies: Mapping[str, AssemblyReport], tool: Mapping[str, str], input_kind: str | None = None) -> dict:
    """The report.json document; `input` names what the assemblies were built from (cpp2il or dummydll)."""
    return {"input": input_kind, "tool": dict(tool), "assemblies": {k: assemblies[k] for k in sorted(assemblies)},
            "disclaimer": DISCLAIMER}
