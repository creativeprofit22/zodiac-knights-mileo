"""Schema check for Il2CppDumper's script.json (the Ghidra/IDA import file). Pure: parsed JSON in, counts out."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# key -> (required fields, optional fields); every Address-like field is an int, the rest str
SECTIONS: dict[str, tuple[dict[str, type], dict[str, type]]] = {
    "ScriptMethod": ({"Address": int, "Name": str, "Signature": str, "TypeSignature": str}, {}),
    "ScriptString": ({"Address": int, "Value": str}, {}),
    "ScriptMetadata": ({"Address": int, "Name": str}, {"Signature": str}),
    "ScriptMetadataMethod": ({"Address": int, "Name": str, "MethodAddress": int}, {}),
}
ADDRESSES = "Addresses"


@dataclass(frozen=True)
class ScriptSummary:
    methods: int
    strings: int
    metadata: int
    metadata_methods: int
    addresses: int

    def as_dict(self) -> dict[str, int]:
        return {"methods": self.methods, "strings": self.strings, "metadata": self.metadata,
                "metadata_methods": self.metadata_methods, "addresses": self.addresses}


def _is(value: object, kind: type) -> bool:
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind)


def _check_entry(entry: object, path: str, required: dict[str, type], optional: dict[str, type]) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{path}: expected an object, got {type(entry).__name__}")
    for key, kind in required.items():
        if key not in entry:
            raise ValueError(f"{path}.{key}: missing")
        if not _is(entry[key], kind):
            raise ValueError(f"{path}.{key}: expected {kind.__name__}, got {type(entry[key]).__name__}")
    for key, kind in optional.items():
        if key in entry and entry[key] is not None and not _is(entry[key], kind):
            raise ValueError(f"{path}.{key}: expected {kind.__name__}, got {type(entry[key]).__name__}")


def validate(data: object) -> ScriptSummary:
    """Check the script.json structure; raise ValueError naming the JSON path of the first problem."""
    if not isinstance(data, dict):
        raise ValueError(f"$: expected an object, got {type(data).__name__}")
    counts: dict[str, int] = {}
    for section, (required, optional) in SECTIONS.items():
        if section not in data:
            raise ValueError(f"$.{section}: missing")
        items = data[section]
        if not isinstance(items, list):
            raise ValueError(f"$.{section}: expected a list, got {type(items).__name__}")
        for i, entry in enumerate(items):
            _check_entry(entry, f"$.{section}[{i}]", required, optional)
        counts[section] = len(items)
    if ADDRESSES not in data:
        raise ValueError(f"$.{ADDRESSES}: missing")
    addrs = data[ADDRESSES]
    if not isinstance(addrs, list):
        raise ValueError(f"$.{ADDRESSES}: expected a list, got {type(addrs).__name__}")
    for i, a in enumerate(addrs):
        if not _is(a, int):
            raise ValueError(f"$.{ADDRESSES}[{i}]: expected int, got {type(a).__name__}")
    return ScriptSummary(counts["ScriptMethod"], counts["ScriptString"], counts["ScriptMetadata"],
                         counts["ScriptMetadataMethod"], len(addrs))


TYPE_INFO = "_TypeInfo"


def strip_generics(name: str) -> str:
    """Drop generic argument lists (`List<Hero>` -> `List`) but keep compiler-generated names (`<Run>d__5`)."""
    out: list[str] = []
    depth = 0
    for i, ch in enumerate(name):
        if depth:
            depth += {"<": 1, ">": -1}.get(ch, 0)
        elif ch == "<" and i > 0 and name[i - 1] not in ".<":
            depth = 1
        else:
            out.append(ch)
    return "".join(out)


def _segments(name: str) -> list[str]:
    """Split on dots outside angle brackets (`<A.B>c` stays one segment)."""
    segs: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in name:
        if ch == "." and depth == 0:
            segs.append("".join(cur))
            cur = []
            continue
        depth += {"<": 1, ">": -1}.get(ch, 0)
        cur.append(ch)
    segs.append("".join(cur))
    return segs


def _owner(method_name: str) -> str:
    return strip_generics(method_name.split("$$", 1)[0])


def type_owners(data: Mapping[str, object]) -> frozenset[str]:
    """Every type name that owns a method or has a TypeInfo, generics stripped; array types skipped."""
    owners: set[str] = set()
    methods = data.get("ScriptMethod", [])
    metadata = data.get("ScriptMetadata", [])
    for entry in methods if isinstance(methods, list) else []:
        if isinstance(entry, dict) and isinstance(name := entry.get("Name"), str) and "$$" in name:
            owners.add(_owner(name))
    for entry in metadata if isinstance(metadata, list) else []:
        if isinstance(entry, dict) and isinstance(name := entry.get("Name"), str) and name.endswith(TYPE_INFO):
            base = name[: -len(TYPE_INFO)]
            if base and "[]" not in base:
                owners.add(strip_generics(base))
    owners.discard("")
    return frozenset(owners)


def resolve_class(method_name: str, owners: frozenset[str]) -> tuple[str, str] | None:
    """(namespace, top-level class) of a `Type$$Method` name: the shortest owner prefix, since namespaces own
    no methods and nested/compiler-generated types belong to their outermost class."""
    if "$$" not in method_name:
        return None
    segs = _segments(_owner(method_name))
    for i in range(1, len(segs) + 1):
        if ".".join(segs[:i]) in owners:
            return ".".join(segs[: i - 1]), segs[i - 1]
    return None
