# Port: `il2cpp_dump` (contract v2)

Module `zk/ports/il2cpp_dump.py`. Changing this contract needs a new ADR ([ADR 0003](../adr/0003-il2cpp-dump-v2.md) made v2).

Turns libil2cpp.so + global-metadata.dat into C# signatures, a Ghidra script and C headers. Perfare Il2CppDumper is not used: it breaks on metadata v39.

## Protocol
```python
class Il2CppDump(Protocol):
    def dump(self, binary: Path, metadata: Path, out: Path) -> dict: ...
```

## Artifact contract
| path | kind | content |
|---|---|---|
| `dump.cs` | file | C# signatures, see [csharp_dump](../formats/csharp_dump.md) |
| `script.json` | file | method/string/metadata addresses, see [il2cpp_script](../formats/il2cpp_script.md) |
| `il2cpp.h` | file | C structs for the game types |
| `summary.json` | file | `{"assemblies": {"<Asm>": {"types", "methods", "classes": {"<Ns.Type>": methods}}}}`, sorted keys, names normalized (see Notes) |
| `DummyDll/` | folder | one stub `<Assembly>.dll` per assembly |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| `il2cppdumper` | AndnixSH Il2CppDumper 3.2.1 (`--no-pause`, on the pinned .NET 10 runtime) | default |

## Notes
- The adapter fails on a non-zero exit, on error or exception text in the output, on a missing contract file or on an invalid `script.json`.
- `summary.json` names follow the normative rules in [csharp_dump](../formats/csharp_dump.md#layout), so both dumpers compare. The `code` stage fails on a type mismatch, so an adapter must apply all of them:
  - Assembly names drop `.dll` and `.cs`.
  - Generic names become ``Name`N`` (`Hero<T>` becomes ``Hero`1``).
  - Every other character that is not a letter, digit, `_`, `.` or backtick becomes `_`: `<>c` becomes `__c`, `<PrivateImplementationDetails>` becomes `_PrivateImplementationDetails_`, `__StaticArrayInitTypeSize=12` becomes `__StaticArrayInitTypeSize_12`.
  - `<Module>` is left out.
  - Nested types are `Ns.Outer.Inner`; a nested type listed with an empty namespace borrows its outer type's namespace.
  - In `dump.cs`, a type is a line with `// TypeDefIndex: N`, and its assembly comes from the image header ranges.
  - A method is a line with `(` directly inside a type body (constructors included); fields and `/* GenericInstMethod */` blocks don't count.
  - Property and event accessors (`get_X`, `add_X`, or `get;`, `set;`, `add;`, `remove;` inside a property or event) count as methods.
  - `types` counts declarations, not distinct names, so it can exceed `len(classes)` when names collide.
  - A `delegate` declaration counts as a type.
  - Keys are sorted.
