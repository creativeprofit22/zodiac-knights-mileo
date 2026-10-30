"""Summaries of C# signature dumps: types and methods per assembly, normalized so two dumpers compare.

Shape: {"assemblies": {name: {"types": n, "methods": n, "classes": {"Ns.Outer.Inner": methods}}}}.
Assembly names drop ".dll"; generic names become Name`N; nested types are Outer.Inner; any other character that is
not a letter, digit or `_` becomes `_` (Il2CppInspector's spelling: <>c -> __c). `<Module>` is left out, and
property/event accessors count as methods. "types" counts declarations, so a name clash cannot hide a type.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TypedDict

_IMAGE = re.compile(r"^// Image (\d+): (.+?) - (\d+)\s*$")
_TYPEDEF = re.compile(r"//\s*TypeDefIndex:\s*(\d+)")
_NAMESPACE_COMMENT = re.compile(r"^// Namespace:\s*(.*?)\s*$")
_NAMESPACE_BLOCK = re.compile(r"^namespace\s+([\w.]+)")
_KIND = re.compile(r"(?:^|\s)(class|struct|interface|enum|record)\s+(.*)$")
_DELEGATE = re.compile(r"(?:^|\s)delegate\s+(.*)$")
_MANGLE = re.compile(r"[^\w.`]")
# Il2CppInspector writes indexer accessors with bodies: `this[int i] { get => default; set {} }`
_ACCESSOR = re.compile(r"\b(?:get|set|init|add|remove)\s*(?:;|=>|\{)")
# ...and attributes on one accessor: `{ get; [Obsolete("", true)] set; }` (their "(" would read as a method)
_ACCESSOR_ATTRIBUTE = re.compile(r"\[[^\[\]]*\]\s*(?=(?:get|set|init|add|remove)\s*(?:;|=>|\{))")
MODULE = "<Module>"
_STRING = re.compile(r'@?"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')


class AssemblySummary(TypedDict):
    types: int
    methods: int
    classes: dict[str, int]


class Summary(TypedDict):
    assemblies: dict[str, AssemblySummary]


def assembly_name(name: str) -> str:
    for suffix in (".cs", ".dll"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return name


def _split_top(text: str, sep: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in text:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _segment(seg: str) -> str:
    seg = seg.strip()
    if not seg.endswith(">"):
        return seg
    depth = 0
    for i in range(len(seg) - 1, -1, -1):
        depth += {">": 1, "<": -1}.get(seg[i], 0)
        if depth == 0:
            if i == 0:
                return seg  # a compiler name such as <Module>
            return f"{seg[:i]}`{len(_split_top(seg[i + 1:-1], ','))}"
    return seg


def normalize(name: str) -> str:
    """`Outer<T>.Inner<A, B>` -> ``Outer`1.Inner`2``; names already in backtick form stay."""
    return _MANGLE.sub("_", ".".join(_segment(s) for s in _split_top(name.strip(), ".")))


def _decl_name(rest: str) -> str:
    """Text after the class/struct/... keyword -> the type name (base list and constraints dropped)."""
    head = _split_top(rest, ":")[0]
    head = re.split(r"\s+where\s+", head)[0]
    return head.strip().rstrip("{").strip()


def _code(line: str) -> str:
    """Strip string literals and a trailing // comment."""
    line = _STRING.sub('""', line)
    cut = line.find("//")
    return line[:cut] if cut >= 0 else line


def _strip_attributes(code: str) -> str:
    code = code.strip()
    while code.startswith("["):
        depth = 0
        for i, ch in enumerate(code):
            depth += {"[": 1, "]": -1}.get(ch, 0)
            if depth == 0:
                code = code[i + 1:].strip()
                break
        else:
            return ""
    return code


def _type_decl(code: str) -> str | None:
    m = _KIND.search(code)
    if m is None or "(" in code[: m.start()]:  # `where T : class` on a method is not a type
        return None
    return _decl_name(m.group(2))


def _is_method(code: str) -> bool:
    return "(" in code and not code.startswith(("namespace ", "using "))


def _uncomment_blocks(lines: list[str]) -> list[str]:
    """Blank out /* ... */ blocks (Il2CppDumper's GenericInstMethod lists)."""
    out: list[str] = []
    inside = False
    for line in lines:
        s = line.strip()
        if inside:
            out.append("")
            inside = "*/" not in s
        elif s.startswith("/*"):
            out.append("")
            inside = "*/" not in s
        else:
            out.append(line)
    return out


def _finish(assemblies: dict[str, dict[str, int]], declared: Mapping[str, int]) -> Summary:
    result: dict[str, AssemblySummary] = {}
    for asm in sorted(assemblies):
        classes = dict(sorted(assemblies[asm].items()))
        result[asm] = {"types": declared.get(asm, 0), "methods": sum(classes.values()), "classes": classes}
    return {"assemblies": result}


def summarize_dumper(text: str) -> Summary:
    """Il2CppDumper dump.cs: `// Image N: X.dll - start` headers map TypeDefIndex ranges to assemblies."""
    lines = _uncomment_blocks(text.splitlines())
    images: list[tuple[int, str]] = []
    for line in lines:
        if m := _IMAGE.match(line):
            images.append((int(m.group(3)), assembly_name(m.group(2))))
    images.sort()
    if not images:
        raise ValueError("dump.cs has no `// Image N: name - start` header lines")

    def image_of(index: int) -> str:
        found = images[0][1]
        for start, name in images:
            if start > index:
                break
            found = name
        return found

    found: list[list[str | int]] = []  # [assembly, namespace, raw name, methods]
    namespace = ""
    current: list[str | int] | None = None
    depth = 0
    for line in lines:
        if depth == 0 and (m := _NAMESPACE_COMMENT.match(line)):
            namespace = m.group(1)
            continue
        code = _strip_attributes(_code(line))
        if (m := _TYPEDEF.search(line)) and (name := _type_decl(code)) is not None:
            current = [image_of(int(m.group(1))), namespace, name, 0]
            if name != MODULE:
                found.append(current)
        elif current is not None and depth == 1 and _is_method(code):
            current[3] = int(current[3]) + 1
        depth += code.count("{") - code.count("}")
        if depth <= 0:
            depth = 0
            if code.strip().endswith("}"):
                current = None

    # nested types come out as `Outer.Inner` with an empty namespace: borrow the top-level outer's namespace
    top: dict[str, dict[str, str]] = {name: {} for _, name in images}
    for asm, ns, name, _ in found:
        if ns:
            top[str(asm)].setdefault(normalize(str(name)), normalize(f"{ns}.{name}"))
    assemblies: dict[str, dict[str, int]] = {name: {} for _, name in images}
    declared: dict[str, int] = {name: 0 for _, name in images}
    for asm, ns, name, methods in found:
        asm = str(asm)
        full = normalize(f"{ns}.{name}" if ns else str(name))
        if not ns and "." in full:
            outer, inner = full.split(".", 1)
            owner = top[asm].get(outer) or next((v for k, v in sorted(top[asm].items())
                                                 if k.split("`", 1)[0] == outer), None)
            if owner is not None:
                full = f"{owner}.{inner}"
        assemblies[asm][full] = assemblies[asm].get(full, 0) + int(methods)
        declared[asm] += 1
    return _finish(assemblies, declared)


def summarize_inspector(files: Mapping[str, str]) -> Summary:
    """Il2CppInspector C# output with one file per assembly ({file name: text}); types nest in braces."""
    assemblies: dict[str, dict[str, int]] = {}
    declared: dict[str, int] = {}
    for fname in sorted(files):
        asm = assembly_name(fname.replace("\\", "/").rsplit("/", 1)[-1])
        classes = assemblies.setdefault(asm, {})
        declared.setdefault(asm, 0)
        scopes: list[tuple[str, str]] = []  # (kind, name) for each open brace: ns, type or other
        pending: tuple[str, str] | None = None
        for line in _uncomment_blocks(files[fname].splitlines()):
            code = _ACCESSOR_ATTRIBUTE.sub("", _strip_attributes(_code(line)))
            if not code:
                continue
            in_type = bool(scopes) and scopes[-1][0] == "type"
            if m := _NAMESPACE_BLOCK.match(code):
                pending = ("ns", m.group(1))
            elif (dm := _DELEGATE.search(code)) and "(" in code:
                name = _decl_name(dm.group(1).split("(", 1)[0].split()[-1])
                classes.setdefault(_full(scopes, name), 0)
                declared[asm] += 1
            elif (name := _type_decl(code)) is not None and name == MODULE:
                pending = ("other", "")
            elif name is not None:
                pending = ("type", name)
                classes.setdefault(_full(scopes, name), 0)
                declared[asm] += 1
            elif in_type and _is_method(code):
                classes[_full(scopes, "")] += 1
            # accessors only inside a property/event block or a one-line `{ get; set; }`: a field named `add;` is not one
            elif ((scopes and scopes[-1][0] == "other") or "{" in code)                     and (n := len(_ACCESSOR.findall(code))) and (owner := _owner(scopes)) is not None:
                classes[owner] += n
            for ch in code:
                if ch == "{":
                    scopes.append(pending or ("other", ""))
                    pending = None
                elif ch == "}" and scopes:
                    scopes.pop()
    return _finish(assemblies, declared)


def _owner(scopes: list[tuple[str, str]]) -> str | None:
    """Full name of the innermost type around the current line (property/event blocks are "other" scopes)."""
    for i in range(len(scopes) - 1, -1, -1):
        if scopes[i][0] == "type":
            return _full(scopes[: i + 1], "")
    return None


def _full(scopes: list[tuple[str, str]], name: str) -> str:
    parts = [n for kind, n in scopes if kind in ("ns", "type")]
    if name:
        parts.append(name)
    return normalize(".".join(parts))
