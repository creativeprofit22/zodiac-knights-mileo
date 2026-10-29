# ADR 0004: `decompiler` contract v2 (C#), `java_decompiler` and `il2cpp_assemblies`

Status: accepted (amends the `decompiler` part of ADR 0001)

## Context

ADR 0001 named the jadx boundary `decompiler` (contract v1: APK in, `sources/` out). The game logic lives in the IL2CPP side, though, and the readable-C# phase needs a decompiler over .NET assemblies (ilspycmd). IL2CPP ships no IL, so those assemblies must first be rebuilt from `libil2cpp.so` + `global-metadata.dat` (Cpp2IL), or taken from the dumper's `DummyDll/`. Building assemblies and decompiling them are separate tools with separate pins, and `[adapters]` holds one adapter per port.

## Decision

- The Java/Kotlin boundary is renamed `java_decompiler` (contract v1, unchanged): `decompile(apk, out) -> dict`, `dirs=("sources",)`. jadx implements it.
- A new port `il2cpp_assemblies` (v1): `build(binary, metadata, unity_version, out) -> dict`, `dirs=("assemblies",)`, one `<Asm>.dll` per assembly. Cpp2IL implements it.
- `decompiler` becomes contract v2, a C# decompiler over assemblies: `decompile(assemblies, names, out) -> dict`, `files=("report.json",)`, `dirs=("projects",)`. It writes `projects/<Asm>/` (a C# project per named assembly) and `report.json` ([csharp_project](../formats/csharp_project.md)). ilspycmd implements it.

## Consequences

- `zk.toml` files must change `decompiler = "jadx"` to `java_decompiler = "jadx"`. An old file fails clearly: jadx declares `PORT = "java_decompiler"`, so `ctx.adapter("decompiler")` raises a port mismatch.
- The `code` stage's manifest `adapters` key is `java_decompiler` from the next `zk code` run on.
- The `csharp` stage uses `il2cpp_assemblies` + `decompiler` and never names either tool.
