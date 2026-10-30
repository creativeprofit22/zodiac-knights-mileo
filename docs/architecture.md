# Architecture

`zk` is a **stage pipeline with ports at the external-tool boundaries** ([ADR 0001](adr/0001-pipeline-with-ports.md); `device_source` contract v2 in [ADR 0002](adr/0002-device-source-v2.md); `il2cpp_dump` v2 and `il2cpp_crosscheck` in [ADR 0003](adr/0003-il2cpp-dump-v2.md); `decompiler` v2, `java_decompiler` and `il2cpp_assemblies` in [ADR 0004](adr/0004-decompiler-v2.md); `ghidra` v2 in [ADR 0005](adr/0005-ghidra-v2.md); `type_info` v2 in [ADR 0006](adr/0006-type-info-v2.md); `video_encoder` in [ADR 0007](adr/0007-video-encoder.md)). Each stage reads workspace folders and writes its own. Any third-party tool (adb, an IL2CPP dumper, jadx, Ghidra…) is reached through a port, and `zk.toml` picks the adapter for each port.

## Layout

```
src/zk/
  core/        pure stdlib building blocks
    workspace.py   workspace areas + manifest.json (stage results, game facts)
    contracts.py   ArtifactContract: files/dirs a port promises in its output folder
    config.py      zk.toml loader (workspace, tools, package, [adapters])
    adapters.py    resolves a port's configured adapter module (no static imports)
    context.py     Context(cfg, ws) + ctx.adapter(port)
    codehash.py    code hash (in-package import closure) + update fingerprint parts
    runner.py      run_stage: execute a stage and record its result in the manifest
    pins.py        Tool + TOOLS: pinned tool versions, URLs and sha256
    toolchain.py   pinned tools: download, sha256 check, unpack into tools/ (adapters only)
  ports/       one module per port: PORT name, runtime_checkable Protocol, CONTRACT; PORTS registry
  adapters/    one module or package per tool, e.g. adapters/jadx.py; chosen in zk.toml
  stages/      one module or package per stage; STAGE_MODULES registry
  formats/     pure parsers: bytes in, data out
  steps.py     the `zk update` plan as data: one Step per stage
  update.py    `zk update` orchestrator (no stage knowledge)
  cli.py       `zk status`, `zk tools`, `zk update`, `zk <stage>`
```

## Data flow

```
device ─device_source (acquire)─▶ raw/<v>/apk/base.apk ─unpack─▶ unpacked/<v>/<stem>/
   unpacked ─il2cpp_dump───────▶ il2cpp/<v>/            (dump.cs, script.json, il2cpp.h, summary.json, DummyDll/)  ┐
   unpacked ─il2cpp_crosscheck─▶ il2cpp/<v>/crosscheck/ (summary.json) → crosscheck.json                        ├ zk code
   raw apk  ─java_decompiler───▶ code/<v>/              (sources/)                                              ┘
   unpacked ─il2cpp_assemblies─▶ csharp/<v>/assemblies/ ┐                     (or il2cpp/<v>/DummyDll/ with --input dummydll)
   assemblies ─decompiler──────▶ csharp/<v>/            ┴ zk csharp            (projects/<Asm>/, report.json, README.md)
   il2cpp + MonoBehaviour classes ─type_info──▶ types/<v>/ (nodes.json)
   lib + il2cpp ─ghidra──▶ ghidra/<v>/   (project/, functions/<Ns>/<Class>.c, index.json)  zk ghidra
   unpacked Data + types ─(UnityPy)──▶ assets/<v>/ (PNG, WAV, fonts, text, shaders.json, MonoBehaviour JSON, scenes)  zk assets
   unpacked assets/Video (.rgbv, .mp4, manifest.json) ──▶ assets/<v>/video/ (frames, report.json)  zk video
   video frames ─video_encoder (--encode)──▶ assets/<v>/video/<clip>/encoded.mp4
   formats parse raw/unpacked bytes ──▶ data/<v>/
```

Workspace areas (`zk.core.workspace.STAGE_DIRS`): `raw`, `unpacked`, `il2cpp`, `code`, `csharp`, `types`, `ghidra`, `assets`, `data`. Each one is created on demand as `workspace/<area>/<version>/`.

## Manifest

`workspace/manifest.json` maps each key to a JSON object:

```json
{
  "game": {"version": "0.4.6-17", "package": "com.zodiacknights.game", "unity_version": "6000.3.2f1",
           "metadata_version": 39, "backend": "il2cpp", "abis": ["arm64-v8a", "armeabi-v7a", "x86_64"]},
  "<stage>": {"...": "stage info", "code_hash": "<sha256>",
              "adapters": {"<port>": {"adapter": "<zk.toml value>", "module": "<module>"}}}
}
```

- `game` holds facts discovered about the build, recorded with `ws.record_facts({...})` and read with `ws.fact(name)` or `ws.current_version()`. Facts such as versions are never hard-coded as constants. A missing fact raises a clear error.
- `zk <stage>` runs `execute(ctx, args)` through `core.runner.run_stage` and then records its info plus `code_hash` and `adapters`, replacing the previous record (and so any `update_stamp`). If the stage raises, nothing is recorded. A `RuntimeError` exits with code 2.
- `code_hash` covers the **in-package import closure** of the stage module and of every adapter module used in that run: each file is parsed with `ast` and only `zk.*` imports that are modules are followed. A stage or adapter that is a package contributes its whole folder (so Ghidra's `.java` scripts count). `zk.core.pins` is left out on purpose; see [Update](#update). Line endings are normalised first, so the hash is the same on Windows and Linux.
- `update` holds the last `zk update` report (see below), so no stage may be named `update`.

## Update

`zk update [--from STEP] [--force] [--dry-run]` runs every stage in order, skipping the ones that are current ([runbook](runbook.md) for day-to-day use). Modelled on SSA's `update.py`.

- **Steps are data.** `zk.steps.STEPS` declares what each step `uses` from its upstream steps (`Uses`: files, bulk trees and manifest record values; `Step.after` is derived from it), outputs, `--force` argv, report fields, checks, warnings and time estimate. `zk.update` reads only those fields and holds no stage names (a test checks this). A stage that reads an upstream output must declare it in `uses`, or update may wrongly skip it.
- **Fingerprint parts** (`codehash.fingerprint_parts`): the code hash, the adapter chosen for each port the stage used, the pinned tools those adapters (and the stage) list in `PINNED` with version and sha256, the versions of pip packages listed in `PACKAGES`, and the `[options.<port>]` values of those ports. Adapter modules are loaded, never created, so planning touches no device and downloads nothing. Because pins reach a step only through `PINNED`, bumping `jadx` reruns `code` but not `ghidra`.
- **Inputs**: game version, the step's argv, and `consumed`: digests of what it uses from each upstream. Files get a content sha256; bulk trees (`assets/bin/Data`, `assets/Video`) get a size+mtime manifest, since they only change when unpack reruns. Each stamp keeps a `file_cache` (`{path: [size, mtime_ns, sha256]}`), so a file whose size and mtime are unchanged is not read again, and each file is hashed at most once per run. So a step reruns after an upstream only if what it consumes changed: a code-only fix that rewrites identical `script.json` and `il2cpp.h` doesn't rerun ghidra.
- **Current** means the record has an `update_stamp` whose parts and inputs match and every declared output exists. Otherwise the step runs, and the plan says why (`no stamp`, `code changed`, `adapter ghidra: a->b`, `pinned tool jadx 1.5.5->1.5.6`, `option ghidra.decompile_timeout changed`, `version a->b`, `code output il2cpp/<v>/il2cpp.h changed`, `missing ghidra/<v>/index.json`, `--force`). Each step is decided just before it would run, after its upstreams ran. A dry run can't know yet, so a step whose only trigger is an upstream that will run shows `maybe` (`reruns if code output changes`).
- **Stamp**: after a step succeeds, `update_stamp = {fingerprint, parts, inputs, result, seconds, at, file_cache}` is written into its record; `file_cache` is present only for steps that consume files. `fingerprint = sha256(parts + inputs + result keys)`, so `file_cache` is not part of it. Stamps written before `consumed` existed (inputs hold `upstream` fingerprints) are adopted without a rerun when the old rule still holds (parts, version and argv unchanged, outputs present, upstream fingerprints unchanged, no upstream rerunning); a real run then rewrites them in the new format. A manual `zk <stage>` drops the stamp, and so does a failure.
- **Source step** (`acquire`): always runs, since only the device knows its version; it counts as skipped when its result (`version`, `base_apk`) is unchanged. A dry run doesn't ask the device and plans downstream steps as if the source were unchanged.
- **Failure**: stops at the first failing step, prints `rerun: zk <step> ...` and `resume: zk update --from <step>`, marks later steps `not run` and exits 2.
- **Report**: version, start time, totals, one row per step (status, reason, seconds, counts), checks and warnings. Printed once at the end and stored in the manifest under `update`.

## Adapter selection

```toml
[adapters]
il2cpp_dump = "mydumper"          # loads zk.adapters.mydumper
decompiler  = "some.pkg.module"   # dotted value: that module
```

An adapter module exposes `PORT = "<port>"` and `create(cfg)`. `ctx.adapter(port)` imports the module and checks that `PORT` matches. It then calls `create(cfg)` and checks the result against the port's Protocol. Each failure gives a clear `RuntimeError`: port not configured, module missing, wrong `PORT`, or Protocol mismatch. Swapping a tool is a one-line config change.

Without `--config`, `zk` reads `zk.toml` at the repo root in a source checkout (a folder with `pyproject.toml` and `src/zk/`), or `./zk.toml` in the current folder when installed; `workspace/` and `tools/` default next to it.

Adapter settings go in `[options.<port>]` tables of strings (e.g. `[options.device_source] path`, `version` for the `folder` adapter), exposed as `cfg.options[port]`.

`Config.load` rejects unknown top-level keys and unknown port names in `[adapters]` and `[options]` with a `RuntimeError` listing the valid ones.

## Dependency rule

Enforced by `tests/test_boundaries.py`, which reads imports with `ast` and resolves relative imports:

| package | must not import |
|---|---|
| `zk.core`, `zk.formats`, `zk.ports` | `zk.stages`, `zk.adapters`, `zk.cli` |
| `zk.stages` | `zk.adapters`, `zk.core.toolchain`, `zk.cli` |
| `zk.adapters` | `zk.stages`, `zk.cli` |
| `zk.update` | `zk.adapters`, `zk.cli` |
| `zk.steps` | `zk.adapters`, `zk.stages`, `zk.cli` |

Stages depend only on port Protocols and artifact contracts, never on a concrete adapter or tool.

## How to add…

- **a stage**: create `zk/stages/<name>.py` with a unique `NAME` (not `game`, `status` or `tools`; `zk` exits 2 otherwise), `HELP`, optional `add_arguments(parser)` and `execute(ctx, args) -> dict`. Append it to `STAGE_MODULES` and add its `Step` to `zk.steps.STEPS` in the same position. Get tools via `ctx.adapter("<port>")`, then call `PORTS["<port>"].contract.verify(out)`. Add a page from `docs/stages/_template.md`.
- **an adapter**: create `zk/adapters/<tool>.py` (or a package) with `PORT` and `create(cfg)`. Fetch the tool via `zk.core.toolchain.path_of`, add its entry to `TOOLS` in `zk/core/pins.py`, and list it in the adapter's `PINNED` (plus pip packages in `PACKAGES`). Every entry must carry a `sha256` of the downloaded file; `fetch` refuses to download a tool without one. Set it in `zk.toml`. Its output must satisfy the port's `CONTRACT`.
- **a port**: create `zk/ports/<port>.py` with `PORT`, the Protocol and `CONTRACT`. Register it in `PORTS` and add a page from `docs/ports/_template.md`. Changing a port contract needs a new ADR (as `device_source` v2 did in ADR 0002).
- **a format**: create `zk/formats/<format>.py` as a pure function over bytes or paths, with no tools and no workspace. Test it with synthetic bytes and add a page from `docs/formats/_template.md`.
