"""ScriptingAssemblies.json: the managed assemblies a Unity player loads ({"names": [...], "types": [...]})."""
from __future__ import annotations

import json
from dataclasses import dataclass

USER_ASSEMBLY = 16  # type 2 = engine module, 16 = user and package assemblies
NON_GAME_PREFIXES = ("Unity", "System", "Mono", "mscorlib", "netstandard")


@dataclass(frozen=True)
class ScriptingAssemblies:
    names: tuple[str, ...]
    types: tuple[int, ...]


def parse(text: str) -> ScriptingAssemblies:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("ScriptingAssemblies.json: expected an object")
    names, types = data.get("names"), data.get("types")
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError("ScriptingAssemblies.json: 'names' must be a list of strings")
    if not isinstance(types, list) or not all(isinstance(t, int) for t in types):
        raise ValueError("ScriptingAssemblies.json: 'types' must be a list of integers")
    if len(names) != len(types):
        raise ValueError(f"ScriptingAssemblies.json: {len(names)} names but {len(types)} types")
    return ScriptingAssemblies(tuple(names), tuple(types))


def game_assemblies(sa: ScriptingAssemblies) -> list[str]:
    """User assemblies that are not Unity, .NET or Mono libraries, without the .dll suffix."""
    return sorted({n.removesuffix(".dll") for n, t in zip(sa.names, sa.types)
                   if t == USER_ASSEMBLY and not n.startswith(NON_GAME_PREFIXES)})
