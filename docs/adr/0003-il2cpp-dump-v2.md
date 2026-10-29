# ADR 0003: `il2cpp_dump` contract v2 and the `il2cpp_crosscheck` port

Status: accepted (amends the `il2cpp_dump` part of ADR 0001)

## Context

Contract v1 promised `dump.cs`, `script.json` and `DummyDll/`. The code-dump phase needs two more things from the dumper:

- `il2cpp.h`. AndnixSH Il2CppDumper writes it next to `script.json`, and the Ghidra phase reads both from one place.
- A per-assembly summary of types and methods. The manifest records it, and the cross-check compares it.

The cross-check runs a second, independent dumper (Il2CppInspectorRedux). `[adapters]` holds one adapter per port, so a second dumper cannot share the `il2cpp_dump` port.

## Decision

- The `il2cpp_dump` CONTRACT becomes `files=("dump.cs", "script.json", "il2cpp.h", "summary.json")`, `dirs=("DummyDll",)`. The Protocol is unchanged: `dump(binary, metadata, out) -> dict`.
- `summary.json` is normalized (sorted keys):
  `{"assemblies": {"<Asm>": {"types": n, "methods": n, "classes": {"<Ns.Type>": method_count}}}}`.
  Assembly names drop `.dll`, and nested types are written `Outer.Inner`.
  Amendment: the full normalization rules live in [csharp_dump](../formats/csharp_dump.md#layout). They were tightened after the first real run (generic ``Name`N``, `<>c` → `__c`, no `<Module>`, accessors count as methods, `types` counts declarations); the contract files are unchanged.
- A new port `il2cpp_crosscheck` has the Protocol `crosscheck(binary, metadata, out) -> dict` and `CONTRACT files=("summary.json",)`, with the same summary shape. The stage compares the two summaries and never names either tool.
- `type_info` stays as it is, for a later phase. `il2cpp.h` now also comes from the dumper; `type_info` may still produce a better header.

## Consequences

- Every `il2cpp_dump` adapter must write `il2cpp.h` and `summary.json`. The only existing ones are test fakes, which are updated.
- Swapping the cross-check tool is a one-line `zk.toml` change, like any other port.
