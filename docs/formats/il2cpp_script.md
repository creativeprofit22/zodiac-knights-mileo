# Format: `il2cpp_script`

Module `zk/formats/il2cpp_script.py`. A pure checker: parsed JSON in, counts out. It uses no tools and no workspace.

## Where it appears
`il2cpp/<v>/script.json`, written by Il2CppDumper (the `il2cpp_dump` port). Ghidra and IDA import scripts read it to name functions, strings and metadata globals.

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

## Evidence
The key names come from the Il2CppDumper `ScriptJson` output class. They are re-checked against the real 0.4.6-17 dump in the `code` stage run.

## Tests
`tests/test_il2cpp_script.py` covers a valid file, a missing section, a wrong top-level type, a bad nested entry, a bool address and a non-object root.
