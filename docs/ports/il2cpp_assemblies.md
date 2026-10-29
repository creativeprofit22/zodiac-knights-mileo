# Port: `il2cpp_assemblies` (contract v1)

Module `zk/ports/il2cpp_assemblies.py`. Changing this contract needs a new ADR. Introduced in [ADR 0004](../adr/0004-decompiler-v2.md).

Rebuilds .NET assemblies (types, fields, signatures and attributes, but no real bodies) from an IL2CPP binary + `global-metadata.dat`, as input for the [decompiler](decompiler.md) port.

## Protocol
```python
class Il2CppAssemblies(Protocol):
    def build(self, binary: Path, metadata: Path, unity_version: str, out: Path) -> dict: ...
```

## Artifact contract
| path | kind | content |
|---|---|---|
| `assemblies/` | folder | one `<Asm>.dll` per assembly (game, Unity and BCL) |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| `cpp2il` | Cpp2IL 2022.1.0-pre-release.21 (self-contained Windows exe), `--force-binary-path --force-metadata-path --force-unity-version --output-as dummydll --output-to <out>/assemblies` | default |

## Notes
- `unity_version` is the `game.unity_version` fact recorded by `zk unpack`.
- Cpp2IL loads plugins from its working directory, so it runs inside `out`. Output goes to `cpp2il.log`. A non-zero exit, or no `*.dll`, raises `RuntimeError`. Stale `assemblies/` is removed first.
- Metadata v39: checked on this game (0.4.6-17). Pre-release.21 logs "Using actual IL2CPP Metadata version 39" and writes 53 assemblies, so no development-commit build is needed. If a later game version breaks it, the fallback is a build from a pinned development commit, recorded with its sha.
