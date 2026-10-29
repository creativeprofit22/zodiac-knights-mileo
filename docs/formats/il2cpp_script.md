# Format: `il2cpp_script`

Module `zk/formats/il2cpp_script.py`. A pure checker: parsed JSON in, counts out. It uses no tools and no workspace.

## Where it appears
`il2cpp/<v>/script.json`, written by Il2CppDumper (the `il2cpp_dump` port). Ghidra and IDA import scripts read it to name functions, strings and metadata globals; the `ghidra` stage also derives its class index from it.

## Layout
| key | type | entry fields | notes |
|---|---|---|---|
| `ScriptMethod` | list | `Address` int, `Name` str, `Signature` str, `TypeSignature` str | one entry per method with code |
| `ScriptString` | list | `Address` int, `Value` str | string literals |
| `ScriptMetadata` | list | `Address` int, `Name` str, `Signature` str (optional, may be null) | TypeInfo and other metadata globals |
| `ScriptMetadataMethod` | list | `Address` int, `Name` str, `MethodAddress` int | MethodInfo globals |
| `Addresses` | list of int | | function start addresses |

Addresses are RVAs. A `bool` is never accepted as an int.

## API
```python
def validate(data: object) -> ScriptSummary: ...  # methods, strings, metadata, metadata_methods, addresses; .as_dict()
```
It raises `ValueError` with the JSON path of the first problem, for example `$.ScriptMethod[3].Address: expected int, got str`.

### Class resolution
```python
def strip_generics(name: str) -> str: ...                 # "List<Hero>" -> "List"; keeps "<Run>d__5"
def type_owners(data: Mapping[str, object]) -> frozenset[str]: ...
def resolve_class(method_name: str, owners: frozenset[str]) -> tuple[str, str] | None: ...
```
`type_owners` is the set of type names that own a method (`ScriptMethod` names before `$$`) or have a `*_TypeInfo` global in `ScriptMetadata`, generics stripped and array types skipped. `resolve_class` maps a `Type$$Method` name to `(namespace, outermost class)` using the **shortest** owner prefix of the dotted type name, because namespaces own no methods and nested or compiler-generated types belong to their outermost class:

| method name | result |
|---|---|
| `ZodiacKnights.Game.AdminLiveOps.<AuthenticateCo>d__54$$MoveNext` | `("ZodiacKnights.Game", "AdminLiveOps")` |
| `ChatModal.ChatEntry$$.ctor` | `("", "ChatModal")` |
| `System.Collections.Generic.List<Hero>$$Add` | `("System.Collections.Generic", "List")` |
| no `$$`, or no owner prefix | `None` |

This needs no `dump.cs`. On 0.4.6-17 it agrees with the `dump.cs` namespace of every ZodiacKnights type and leaves no method unresolved. The `ghidra` stage uses it to pick export targets.

## Evidence
The key names come from the Il2CppDumper `ScriptJson` output class. They are re-checked against the real 0.4.6-17 dump in the `code` stage run.

## Tests
`tests/test_il2cpp_script.py` covers a valid file, a missing section, a wrong top-level type, a bad nested entry, a bool address a non-object root, plus class resolution for nested compiler-generated, generic, global nested, TypeInfo-only and unknown names.
