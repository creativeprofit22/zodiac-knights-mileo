# Format: `csharp_dump`

Module `zk/formats/csharp_dump.py`. A pure parser: text in, summary out. It uses no tools and no workspace.

## Where it appears
- `il2cpp/<v>/dump.cs` from Il2CppDumper (one file, `// Image N: X.dll - <first TypeDefIndex>` headers at the top).
- `il2cpp/<v>/crosscheck/cs/<Assembly>.cs` from Il2CppInspectorRedux (one file per assembly, types nested in `namespace { }` blocks).

Both become the `summary.json` that the `il2cpp_dump` and `il2cpp_crosscheck` contracts require.

## Layout
```json
{"assemblies": {"ZodiacKnights.Game": {"types": 3, "methods": 3,
  "classes": {"ZK.Game.Hero`1": 2, "ZK.Game.Hero`1.Inner`2": 1}}}}
```
Normalization rules, so the two tools compare:
- Assembly names drop `.dll` and `.cs`.
- Generic names become `Name`N` (`Hero<T>` becomes ``Hero`1``).
- Every other character that is not a letter, digit or `_` becomes `_`, which is how Il2CppInspector spells compiler names: `<>c` becomes `__c`, `<PrivateImplementationDetails>` becomes `_PrivateImplementationDetails_`, `__StaticArrayInitTypeSize=12` becomes `__StaticArrayInitTypeSize_12`.
- `<Module>` is left out. Il2CppInspector never prints it.
- Nested types are `Ns.Outer.Inner`. Il2CppDumper writes nested types as `Outer.Inner` with an empty namespace, often before the outer type, so the outer type's namespace is borrowed after the whole file is read.
- In `dump.cs`, a type is a line with `// TypeDefIndex: N`. Its assembly comes from the image header ranges.
- A method is a line with `(` directly inside a type body (constructors included). Fields and `/* GenericInstMethod */` blocks don't count.
- Il2CppDumper lists property and event accessors (`get_X`, `add_X`) as methods; Il2CppInspector prints them as `get;`, `set;`, `add;`, `remove;` inside the property or event, so each of those counts as one method. They count only inside a property or event block (or a one-line `{ get; set; }`), so a field named `add` or `set` is not a method.
- `types` counts declarations, not distinct names, so a name clash cannot hide a type.
- An Inspector `delegate` line counts as a type with 0 methods. Il2CppDumper prints delegates as classes with their `Invoke` methods, so this shows up as a method gap, not a type gap.
- Keys are sorted.

## API
```python
def summarize_dumper(text: str) -> Summary: ...
def summarize_inspector(files: Mapping[str, str]) -> Summary: ...  # {file name: text}
def normalize(name: str) -> str: ...
def assembly_name(name: str) -> str: ...
```
`summarize_dumper` raises `ValueError` when there are no image headers.

## Evidence
The shapes follow Il2CppDumper and Il2CppInspector C# output. On the real 0.4.6-17 build these rules give identical counts from both tools: ZodiacKnights.Game 1153 types and 4502 methods, ZodiacKnights.Logic 202 types and 787 methods, with no per-class method gaps. Engine and BCL assemblies (System, Unity.*) still differ per assembly, and Il2CppDumper lists a `UnityEngine` image that Inspector does not. The `code` stage compares only the game assemblies.

## Tests
`tests/test_csharp_dump.py` uses one synthetic dump and the matching Inspector files (two images, a generic type, a nested generic type, a compiler-generated nested type printed before its outer type, property and event accessors, `<Module>`, an enum, attributes, string literals with braces, generic-instance comment blocks). Both must give the same summary.
