# Format: `csharp_project`

Module `zk/formats/csharp_project.py`. A pure summarizer: C# source text in, counts out. It uses no tools and no workspace.

## Where it appears
`csharp/<v>/projects/<Asm>/**/*.cs`, written by the [decompiler](../ports/decompiler.md) port. The summary is saved as `csharp/<v>/report.json`.

## Layout
`report.json`:

| field | type | notes |
|---|---|---|
| `input` | `"cpp2il"` \| `"dummydll"` | what the assemblies were built from (set by the `csharp` stage) |
| `tool` | object | `{name, version}` of the decompiler |
| `assemblies` | object | `{<Asm>: {types, methods, bodies: {none, reconstructed, stub}}}`, keys sorted |
| `disclaimer` | string | states that this is a reconstruction, not the original C# |

Counting rules:
- **types**: `class`, `struct`, `interface`, `enum`, `record` and `delegate` declarations, nested types included.
- **methods**: methods, constructors, operators, and property, indexer and event accessors.
- **bodies**:
  - `stub`: the body is only a placeholder. A *default* is `null`, `false`, `default`, `default(...)`, or a zero literal `0` / `0.0` with up to two suffix letters from `f d m u l` (any case), e.g. `0f`, `0L`, `0u`, `0UL`.
    - Block bodies (`STUB_STATEMENTS`): any number of leading `X = <default>;` assignments (`X` is a name or dotted name, e.g. `out` parameters), followed by at most one of: `throw null;`, `throw new [System.]NotImplementedException(...);`, `return <default>;`, or a one-line forwarder `this.Name(args);` / `return this.Name(args);` whose arguments are plain names (e.g. ILSpy's `this.MoveNext();`). So an empty body, or one with only the assignments, is also a stub.
    - Expression bodies (`STUB_EXPRESSION`): `=> ` one of the throws, a bare `<default>`, or a `this.Name(args)` forwarder.
    - Comments are blanked first, so a body whose only content was a comment counts as an empty body, i.e. `stub`. This includes ILSpy's "could not decompile" error comments.
  - `none`: there is no body (abstract, extern, interface members, auto accessors), or the accessor only uses the C# 14 `field` keyword (`AUTO_ACCESSOR`): `return field;`, `field = value;` or `=> field`.
  - `reconstructed`: anything else.

Comments, strings, chars and preprocessor lines are blanked before counting.

## API
```python
def summarize_source(text: str) -> AssemblyReport: ...
def summarize(files: Mapping[str, str]) -> dict[str, AssemblyReport]: ...   # {"<Asm>/<path>.cs": text}
def report(assemblies, tool, input_kind=None) -> dict: ...                 # the report.json document
```

## Evidence
Built against ilspycmd 11.2 output on this game (0.4.6-17). The stub patterns are the real Cpp2IL shapes: `return null|false|0|0f|0L|default;`, `out` parameters set to null/default first, and ILSpy's one-line `this.X(...)` forwarders. C# 14 `field` accessors count as `none`. Results:

| input | assembly | types | methods | stub | reconstructed | none |
|---|---|---|---|---|---|---|
| cpp2il | ZodiacKnights.Game | 596 | 2634 | 2448 | 0 | 186 |
| cpp2il | ZodiacKnights.Logic | 127 | 412 | 381 | 0 | 31 |
| dummydll | ZodiacKnights.Game | 687 | 2567 | 2448 | 0 | 119 |
| dummydll | ZodiacKnights.Logic | 124 | 486 | 485 | 0 | 1 |

`types` counts the type declarations in the C# source (nested included, one partial per file). It is not the Il2CppDumper `types` count, which also includes compiler-generated and generic instance entries.

## Tests
`tests/test_csharp_project.py` uses synthetic C#: stub, reconstructed and abstract bodies, nested and generic types, file-scoped namespaces and records.
