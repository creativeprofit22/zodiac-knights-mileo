# Port: `type_info` (contract v2)

Module `zk/ports/type_info.py`. Changing this contract needs a new ADR ([ADR 0006](../adr/0006-type-info-v2.md) made v2).

Assembly + class name in, Unity type-tree nodes out. The `assets` stage needs them because this build ships no type trees, so MonoBehaviours can only be read with generated nodes. Output goes to `types/<version>/`.

## Protocol
```python
class TypeInfo(Protocol):
    def types(self, binary: Path, metadata: Path, dump_dir: Path, unity_version: str,
              classes: Path, out: Path) -> dict: ...
```
- `binary`, `metadata`: `libil2cpp.so` and `global-metadata.dat` from `unpacked/<v>/`.
- `dump_dir`: the [il2cpp_dump](il2cpp_dump.md) output (`DummyDll/`).
- `unity_version`: the `unity_version` fact from the unpack manifest (e.g. `6000.3.2f1`), never a constant.
- `classes`: JSON list written by the stage, `[{"assembly": "UnityEngine.UI", "class": "UnityEngine.UI.Image"}, ...]`; `"reference": true` marks a `[SerializeReference]` payload class (nodes without MonoBehaviour base fields).

Adapters use only the inputs they need.

## Artifact contract
| path | kind | content |
|---|---|---|
| `nodes.json` | file | `{"unity_version", "classes": {"<asm>\|<fullname>": [{"m_Type", "m_Name", "m_Level", "m_MetaFlag"}, ...]}, "missing": {"<asm>\|<fullname>": "<error>"}}`, sorted keys; each requested class is in exactly one of `classes` or `missing`; references likewise go to `references` or `missing_references` |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| `typetree_dummydll` | TypeTreeGeneratorAPI 0.0.10 (`load_dll` over every `DummyDll/*.dll`, sorted) | default |
| `typetree_cpp2il` | TypeTreeGeneratorAPI 0.0.10 `load_il2cpp(binary, metadata)` (Cpp2IL) | disabled: fails on metadata v39 (see Notes) |

## Notes
- TypeTreeGeneratorAPI is MIT and imported lazily (`pip install -e ".[assets]"`).
- Generator fixes applied by both adapters (`zk/adapters/_typetree.py`): a `string[]` field emitted as `string` (with
  `string` elements) is retyped `vector`; reference classes lose the four MonoBehaviour base fields the generator
  prepends to every class. `string_array_fixes` in the adapter info lists where the first fix applied.
- A class the generator can't build goes to `missing` with its error; the stage reports it as `class_missing_in_type_info`.
- Cpp2IL probe (0.4.6-17, arm64-v8a, metadata v39, TypeTreeGeneratorAPI 0.0.10 Windows wheel): the native DLL exports
  `TypeTreeGenerator_loadIL2CPP`, but `load_il2cpp` fails in about 6 s with "Fatal Exception initializing LibCpp2IL!"
  (its Cpp2IL.Core 2022.1.0-pre-release.19 predates v39). `typetree_cpp2il` therefore stays out of `zk.toml`; recheck
  it when TypeTreeGeneratorAPI ships a newer Cpp2IL.
- `typetree_dummydll` probe on the same build: nodes generated and read for 632 of 634 MonoBehaviours.
