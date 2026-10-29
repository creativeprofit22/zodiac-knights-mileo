# Zodiac Knights RE pipeline

`zk` is a reverse-engineering pipeline for Zodiac Knights (Android, Unity/IL2CPP). It runs stages over a workspace, and every external tool sits behind a port.

- [Architecture](architecture.md): layout, data flow, workspace, manifest, adapters, dependency rule
- Decisions: [ADR 0001: pipeline with ports](adr/0001-pipeline-with-ports.md)
- Ports (contract v1): [device_source](ports/device_source.md), [il2cpp_dump](ports/il2cpp_dump.md), [decompiler](ports/decompiler.md), [type_info](ports/type_info.md), [ghidra](ports/ghidra.md)
- Stages: none yet. Each stage phase adds a page from the [stage template](stages/_template.md).
- Formats: none yet. Each parser adds a page from the [format template](formats/_template.md).
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
