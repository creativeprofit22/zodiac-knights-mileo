# zk: Zodiac Knights RE pipeline

`zk` is a modular reverse-engineering pipeline for Zodiac Knights (Android, Unity/IL2CPP). It runs stages over a workspace, and every external tool (adb, IL2CPP dumpers, jadx, ILSpy, Ghidra…) sits behind a port whose adapter is picked in `zk.toml`.

```sh
pip install -e ".[dev]"    # Python >= 3.11
python -m pytest -q        # offline, synthetic data only
zk status                  # configured adapters + workspace manifest
zk tools [names]           # download pinned tools into ./tools
zk update --dry-run        # show what would rerun and why
zk update                  # run every stage, skipping the current ones; prints one report
zk <stage> [...]           # run one stage by hand
```

Workspace: each stage writes to `workspace/<area>/<version>/` (`raw`, `unpacked`, `il2cpp`, `code`, `csharp`, `types`, `ghidra`, `assets`, `video`, `data`), and `workspace/manifest.json` records stage results and game facts; see [Architecture](docs/architecture.md).

Game files (`raw/`, `workspace/`, `tools/`, APKs, `.so`, `global-metadata.dat`) are gitignored and must never be committed.

## Docs

- [Overview](docs/index.md)
- [Architecture](docs/architecture.md): layout, data flow, manifest, update, adapters, dependency rule
- [Runbook](docs/runbook.md): a new game version, importing an APK, swapping an adapter when a tool breaks

Decisions:
[ADR 0001: pipeline with ports](docs/adr/0001-pipeline-with-ports.md),
[ADR 0002: device_source v2](docs/adr/0002-device-source-v2.md),
[ADR 0003: il2cpp_dump v2 + il2cpp_crosscheck](docs/adr/0003-il2cpp-dump-v2.md),
[ADR 0004: decompiler v2 + java_decompiler + il2cpp_assemblies](docs/adr/0004-decompiler-v2.md),
[ADR 0005: ghidra v2](docs/adr/0005-ghidra-v2.md),
[ADR 0006: type_info v2](docs/adr/0006-type-info-v2.md),
[ADR 0007: video_encoder](docs/adr/0007-video-encoder.md)

Stages, in pipeline order:
[acquire](docs/stages/acquire.md),
[unpack](docs/stages/unpack.md),
[code](docs/stages/code.md),
[csharp](docs/stages/csharp.md),
[ghidra](docs/stages/ghidra.md),
[assets](docs/stages/assets.md),
[video](docs/stages/video.md)
([template](docs/stages/_template.md))

Ports:
[device_source](docs/ports/device_source.md),
[il2cpp_dump](docs/ports/il2cpp_dump.md),
[il2cpp_crosscheck](docs/ports/il2cpp_crosscheck.md),
[java_decompiler](docs/ports/java_decompiler.md),
[il2cpp_assemblies](docs/ports/il2cpp_assemblies.md),
[decompiler](docs/ports/decompiler.md),
[type_info](docs/ports/type_info.md),
[ghidra](docs/ports/ghidra.md),
[video_encoder](docs/ports/video_encoder.md)
([template](docs/ports/_template.md))

Formats:
[il2cpp_metadata](docs/formats/il2cpp_metadata.md),
[unity_serialized](docs/formats/unity_serialized.md),
[scripting_assemblies](docs/formats/scripting_assemblies.md),
[il2cpp_script](docs/formats/il2cpp_script.md),
[csharp_dump](docs/formats/csharp_dump.md),
[csharp_dump_diff](docs/formats/csharp_dump_diff.md),
[csharp_project](docs/formats/csharp_project.md),
[rgbv](docs/formats/rgbv.md),
[mp4](docs/formats/mp4.md),
[video_manifest](docs/formats/video_manifest.md)
([template](docs/formats/_template.md))
