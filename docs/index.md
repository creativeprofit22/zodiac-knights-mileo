# Zodiac Knights RE pipeline

`zk` is a reverse-engineering pipeline for Zodiac Knights (Android, Unity/IL2CPP). It runs stages over a workspace, and every external tool sits behind a port.

- [Architecture](architecture.md): layout, data flow, workspace, manifest, adapters, dependency rule
- Decisions: [ADR 0001: pipeline with ports](adr/0001-pipeline-with-ports.md), [ADR 0002: device_source v2](adr/0002-device-source-v2.md), [ADR 0003: il2cpp_dump v2 + il2cpp_crosscheck](adr/0003-il2cpp-dump-v2.md), [ADR 0004: decompiler v2 (C#) + java_decompiler + il2cpp_assemblies](adr/0004-decompiler-v2.md)
- Ports: [device_source](ports/device_source.md) (v2), [il2cpp_dump](ports/il2cpp_dump.md) (v2), [il2cpp_crosscheck](ports/il2cpp_crosscheck.md), [java_decompiler](ports/java_decompiler.md), [il2cpp_assemblies](ports/il2cpp_assemblies.md), [decompiler](ports/decompiler.md) (v2), [type_info](ports/type_info.md), [ghidra](ports/ghidra.md)
- Stages: [acquire](stages/acquire.md), [unpack](stages/unpack.md), [code](stages/code.md), [csharp](stages/csharp.md). New stages start from the [stage template](stages/_template.md).
- Formats: [il2cpp_metadata](formats/il2cpp_metadata.md), [unity_serialized](formats/unity_serialized.md), [scripting_assemblies](formats/scripting_assemblies.md), [il2cpp_script](formats/il2cpp_script.md), [csharp_dump](formats/csharp_dump.md), [csharp_project](formats/csharp_project.md). New parsers start from the [format template](formats/_template.md).
- New port: start from the [port template](ports/_template.md).

## Quick start

```sh
pip install -e ".[dev]"
python -m pytest -q        # offline, synthetic data only
zk status                  # configured adapters + workspace manifest
zk tools [names]           # download pinned tools into ./tools
zk <stage> [...]           # run a stage; records its result in workspace/manifest.json
```

Game files (`raw/`, `workspace/`, `tools/`, APKs, `.so`, `global-metadata.dat`) are gitignored and must never be committed.
