# Architecture

`zk` is a **stage pipeline with ports at the external-tool boundaries** ([ADR 0001](adr/0001-pipeline-with-ports.md); `device_source` contract v2 in [ADR 0002](adr/0002-device-source-v2.md); `il2cpp_dump` v2 and `il2cpp_crosscheck` in [ADR 0003](adr/0003-il2cpp-dump-v2.md); `decompiler` v2, `java_decompiler` and `il2cpp_assemblies` in [ADR 0004](adr/0004-decompiler-v2.md)). Each stage reads workspace folders and writes its own. Any third-party tool (adb, an IL2CPP dumper, jadx, Ghidra…) is reached through a port, and `zk.toml` picks the adapter for each port.

## Layout

```
src/zk/
  core/        pure stdlib building blocks
    workspace.py   workspace areas + manifest.json (stage results, game facts)
    contracts.py   ArtifactContract: files/dirs a port promises in its output folder
    config.py      zk.toml loader (workspace, tools, package, [adapters])
    adapters.py    resolves a port's configured adapter module (no static imports)
    context.py     Context(cfg, ws) + ctx.adapter(port)
    codehash.py    sha256 of the code behind a stage result
    toolchain.py   pinned tools: download, sha256 check, unpack into tools/ (adapters only)
  ports/       one module per port: PORT name, runtime_checkable Protocol, CONTRACT; PORTS registry
  adapters/    one module or package per tool, e.g. adapters/jadx.py; chosen in zk.toml
  stages/      one module or package per stage; STAGE_MODULES registry
  formats/     pure parsers: bytes in, data out
  cli.py       `zk status`, `zk tools`, `zk <stage>`
```

## Data flow

```
device ─device_source (acquire)─▶ raw/<v>/apk/base.apk ─unpack─▶ unpacked/<v>/<stem>/
   unpacked ─il2cpp_dump───────▶ il2cpp/<v>/            (dump.cs, script.json, il2cpp.h, summary.json, DummyDll/)  ┐
   unpacked ─il2cpp_crosscheck─▶ il2cpp/<v>/crosscheck/ (summary.json) → crosscheck.json                        ├ zk code
   raw apk  ─java_decompiler───▶ code/<v>/              (sources/)                                              ┘
   unpacked ─il2cpp_assemblies─▶ csharp/<v>/assemblies/ ┐                     (or il2cpp/<v>/DummyDll/ with --input dummydll)
   assemblies ─decompiler──────▶ csharp/<v>/            ┴ zk csharp            (projects/<Asm>/, report.json, README.md)
   il2cpp   ─type_info───▶ types/<v>/    (il2cpp.h)
   lib + il2cpp ─ghidra──▶ ghidra/<v>/   (index.json, functions/)
   formats parse raw/unpacked bytes ──▶ assets/<v>/, data/<v>/
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
- `zk <stage>` runs `execute(ctx, args)` and then records its info plus `code_hash` and `adapters`. If the stage raises, nothing is recorded. A `RuntimeError` exits with code 2.
- `code_hash` covers the stage module, all of `zk/core`, `zk/ports` and `zk/formats`, and every adapter module used in that run. Line endings are normalised first, so the hash is the same on Windows and Linux.

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

Stages depend only on port Protocols and artifact contracts, never on a concrete adapter or tool.

## How to add…

- **a stage**: create `zk/stages/<name>.py` with a unique `NAME` (not `game`, `status` or `tools`; `zk` exits 2 otherwise), `HELP`, optional `add_arguments(parser)` and `execute(ctx, args) -> dict`. Append it to `STAGE_MODULES`. Get tools via `ctx.adapter("<port>")`, then call `PORTS["<port>"].contract.verify(out)`. Add a page from `docs/stages/_template.md`.
- **an adapter**: create `zk/adapters/<tool>.py` (or a package) with `PORT` and `create(cfg)`. Fetch the tool via `zk.core.toolchain.path_of`, and add its `TOOLS` entry. Every entry must carry a `sha256` of the downloaded file; `fetch` refuses to download a tool without one. Set it in `zk.toml`. Its output must satisfy the port's `CONTRACT`.
- **a port**: create `zk/ports/<port>.py` with `PORT`, the Protocol and `CONTRACT`. Register it in `PORTS` and add a page from `docs/ports/_template.md`. Changing a port contract needs a new ADR (as `device_source` v2 did in ADR 0002).
- **a format**: create `zk/formats/<format>.py` as a pure function over bytes or paths, with no tools and no workspace. Test it with synthetic bytes and add a page from `docs/formats/_template.md`.
