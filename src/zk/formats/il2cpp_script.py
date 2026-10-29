"""Schema check for Il2CppDumper's script.json (the Ghidra/IDA import file). Pure: parsed JSON in, counts out."""
from __future__ import annotations

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
