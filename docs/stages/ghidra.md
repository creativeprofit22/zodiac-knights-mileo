# Stage: `ghidra`

`zk ghidra [--abi ABI] [--skip-analysis] [--filter REGEX] [--limit N] [--force]`, module `zk/stages/ghidra.py`

## Purpose
Builds an analyzed, symbol-named Ghidra project of `libil2cpp.so` and exports decompiled C for each ZodiacKnights class. This is the source of truth for game logic; the C# view from `zk csharp` gives structure only.

## Inputs
- Manifest `unpack` info: `il2cpp[abi]` (the shared `stages/_unpack.py` lookup) for the binary.
- Manifest `code` record for this version, dumped for the same ABI.
- `il2cpp/<v>/` from `zk code` (the [il2cpp_dump](../ports/il2cpp_dump.md) contract). Only `script.json` and `il2cpp.h` are read; the dumper is never called.
- Port: [ghidra](../ports/ghidra.md) (v2). Adapter `ghidra`: Ghidra 12.2 `analyzeHeadless` on the portable JDK 25 (`zk tools ghidra jdk25`).

## Target selection
Classes come from `script.json` alone ([il2cpp_script](../formats/il2cpp_script.md#class-resolution)): each `ScriptMethod` name is resolved to its namespace and outermost class. A class is exported unless its root namespace is in `THIRD_PARTY` (`UnityEngine`, `UnityEngineInternal`, `Unity` — which covers `Unity.Burst`, `Unity.Collections`, `Unity.Mathematics`, `Unity.RenderPipelines`… —, `System`, `Mono`, `Microsoft`, `Internal`, `JetBrains`, `AOT`, `Interop`, `TMPro`, `Firebase`, `Google`, `Kotlin`/`kotlin`, `Newtonsoft`), or it is a global-namespace class matching `THIRD_PARTY_GLOBAL` (`SR`, `Locale`, `Interop`, `UnitySourceGeneratedAssemblyMonoScriptTypes*`, `__JobReflectionRegistrationOutput__*`, `$BurstDirectCallInitializer`, `<PrivateImplementationDetails>`…). `UnityEngine.InputSystem` and `UnityEngine.Timeline` fall under `UnityEngine`.

On 0.4.6-17 this selects 372 classes and 5166 functions, all under `ZodiacKnights` (`ZodiacKnights.Game`, `ZodiacKnights.Logic`). Every selected class is a top-level type in `dump.cs`, no method is unresolved, and the 17 ZodiacKnights types left out are enums and interfaces with no code.

## Outputs
- `ghidra/<v>/targets.tsv`: `rva_hex<TAB><Ns>/<Class>.c`, written by the stage.
- `ghidra/<v>/symbols.tsv`, `il2cpp_ghidra.h`: adapter inputs for the import script (not with `--skip-analysis`).
- `ghidra/<v>/project/libil2cpp.gpr` (+ `libil2cpp.rep/`): the analyzed project.
- `ghidra/<v>/functions/<Ns>/<Class>.c`: one file per class, global classes under `_global/`.
- `ghidra/<v>/index.json`: `{tool, version, jdk, project, classes: {relpath: functions}, missing: [...], failed: {relpath: functions not decompiled}}`; `failed` is counted from the `.c` files, so it stays right after resumed runs.
- `ghidra/<v>/headless.log`, `headless.script.log`: Ghidra and script logs (appended across runs).
- Manifest `ghidra` info:

| key | meaning |
|---|---|
| `version`, `abi` | build label and ABI |
| `skip_analysis`, `filter`, `limit` | the arguments used |
| `classes_targeted`, `functions_targeted` | size of `targets.tsv` |
| `roots` | `{root namespace: classes}`; expected to be only `ZodiacKnights` |
| `analysis` | adapter info: `tool`, `version`, `jdk`, `maxmem`, `decompile_timeout`, `classes_written`, `classes_missing`, `functions_failed` (total of index.json `failed`) |
| `code_hash`, `adapters` | always recorded by the CLI; `code_hash` includes the `.java` scripts |

## How the run works
One `analyzeHeadless` call (stdin closed):
1. imports `libil2cpp.so` into a new project;
2. preScript `Il2CppImport.java` parses `il2cpp_ghidra.h` with Ghidra's `CParser`, then names every method and applies its signature from `symbols.tsv`, and labels strings and metadata globals. It disables the slow `Call Convention ID` and `Decompiler Switch Analysis` analyzers and prints `analyzer option not found: …` if a name no longer exists. A header parse failure throws, so it surfaces as a script error;
3. auto-analysis;
4. postScript `Il2CppExport.java` decompiles the targets with a fixed worker pool (half the cores), each worker with its own long-lived decompiler. Work is scheduled per function, not per class: classes with the most functions are queued first, so a big class is spread over all workers instead of running alone at the end. When a class's last function is done, its blocks are joined in RVA order, written to `<Class>.c.part` and renamed to `<Class>.c`; existing `.c` files are skipped, so an interrupted export resumes.

Every 60 seconds the export prints a progress line (also in `headless.script.log`), counting only this run's work:
```
Il2CppExport: progress 600s: files 0/1, functions 105/110, failed 6
```
It ends with `Il2CppExport: files=1 functions=110 failed=11`.

With `--skip-analysis` the saved project is opened read-only (`-process -noanalysis -readOnly`) and only step 4 runs.

`analyzeHeadless` exits 0 even when the import fails, so success is judged from the log: any `ERROR (HeadlessAnalyzer)` line written by this run fails the stage. Analyzer messages such as `ERROR VarnodeContext: out of address spaces` are normal on large AArch64 binaries and are ignored.

### Header fix-up
`il2cpp.h` (AndnixSH 3.2.1) gets the same treatment as Il2CppDumper's `il2cpp_header_to_ghidra.py`: a prelude of `typedef`s for the MSVC integer types, and `struct X : Base {` turned into `struct X { Base super;`. On 0.4.6-17 the fixed header parses in Ghidra 12.2 without errors (about 5 minutes); no further fix-up was needed. Covered by `tests/test_ghidra.py::test_ghidra_header_rewrites_inheritance`.

## Arguments
| flag | default | meaning |
|---|---|---|
| `--abi` | `arm64-v8a` | which `libil2cpp.so`; must match the `zk code` ABI |
| `--skip-analysis` | off | reuse `project/libil2cpp.gpr` and only export missing `.c` files |
| `--filter` | none | only classes whose `Namespace.Class` matches the regex |
| `--limit` | none | only the first N classes (sorted) |
| `--force` | off | delete `ghidra/<v>/`, including the project, and rerun |

Config in `zk.toml`, `[options.ghidra]`: `maxmem` (default `"12G"`) sets the headless heap (`GHIDRA_HEADLESS_MAXMEM`); `decompile_timeout` (seconds, default `"30"`, this repo sets `"300"`) is the per-function decompiler limit passed to `Il2CppExport.java`.

To re-export one class, delete its `.c` file and run `zk ghidra --skip-analysis`.

## Failure modes
`RuntimeError` (exit 2), and nothing is recorded, when:
- there is no `unpack` record or the ABI is missing (run `zk unpack`);
- there is no `code` record for this version, or it was dumped for another ABI (run `zk code [--abi ABI]`);
- `il2cpp/<v>/` breaks the il2cpp_dump contract or `script.json` fails validation (rerun `zk code --force`);
- `--filter` is not a valid regular expression;
- no class is selected (check `--filter`);
- `--skip-analysis` is used before a full run created the project;
- Ghidra exits non-zero or this run logged `ERROR (HeadlessAnalyzer)` (failed import, script error, header parse error); see `headless.log` and `headless.script.log`;
- the output breaks the ghidra contract.

Classes listed in `index.json` `missing` are not a failure; rerun with `--skip-analysis` to retry them. A function the decompiler cannot finish within `decompile_timeout` is written as a `// decompilation failed: … timeout` comment in its class file. Their count per file is in `index.json` `failed` (total in the manifest `analysis.functions_failed`). To retry, delete the files listed there and rerun with `--skip-analysis`. On 0.4.6-17, 180 of 5166 functions timed out at 30 s; retrying their 43 files at 300 s left 49, and took about 2¼ hours, `GameServer.c` most of it, because the export then decompiled one class's functions one after another.

Re-exporting only `ZodiacKnights.Logic/GameServer.c` (110 functions, 300 s, 6 workers) with `--skip-analysis`: 3846 s (64 min, 9 failed) with one class per worker, 890 s (15 min, 11 failed) with per-function scheduling. More functions decompile at once, so functions close to the limit can time out in one run and not in another. Ghidra's output also depends on what the same decompiler process did before: between runs a few blocks differ only in the numbering of temporaries (`auVar56`/`auVar57`); the code is the same.

A full run needs about 12 GB of heap; on 0.4.6-17 it took about 70 minutes (import + header ~10 minutes, analysis, then ~35 minutes of export). A `--skip-analysis` run with nothing to do takes about 90 seconds. Do not open the project in the GUI while a headless run is going: the project is locked.

## Opening the project in the GUI
1. `zk tools ghidra jdk25` (already done if the stage ran).
2. Point Ghidra at the portable JDK and start it (Windows, from the repo root):
   ```bat
   set JAVA_HOME=%CD%\tools\jdk25-25.0.5+8\jdk-25.0.5+8
   tools\ghidra-12.2\ghidra_12.2_PUBLIC\ghidraRun.bat
   ```
   The stage already pins this JDK in Ghidra's `support/launch.properties`, so `JAVA_HOME` is only needed if that file was reset.
3. File > Open Project > `workspace/ghidra/<v>/project/libil2cpp.gpr`, then open `libil2cpp.so`.
4. Answer **No** when asked to analyze again: the project is already analyzed and named.

## Optional: GhidraMCP
[LaurieWired/GhidraMCP](https://github.com/LaurieWired/GhidraMCP) (Apache-2.0) lets an MCP client browse, decompile and rename in the open project. Its Ghidra 12.x support is unverified, and zk does not install or pin it.
1. Download a GhidraMCP release built for Ghidra 12.2 (the extension zip must match the Ghidra version).
2. In the GUI: File > Install Extensions > `+` > the zip, restart Ghidra.
3. Open the project from the section above, then File > Configure > Developer > enable `GhidraMCPPlugin`.
4. Run `python bridge_mcp_ghidra.py` from the release and register it as an MCP server in your client.

Renames made this way change the saved project; a later `zk ghidra --force` discards them.

## Tests
- `tests/test_ghidra.py`: target selection against Unity 6, BCL and plugin namespaces (only ZodiacKnights survives), `--filter`/`--limit`, `class_relpath`, `symbol_lines`, `ghidra_header`, `headless_cmd` in both modes, `headless_errors`, `run_lines`, `run_logs`, `ghidra_env`, `pin_jdk`, the adapter with an injected runner (success, `ERROR (HeadlessAnalyzer)`, `--skip-analysis` without a project), the 12.2/JDK 25 pins and the packaged scripts (the export keeps `.part`, the `// decompilation failed: ` comment and the timed progress line).
- `tests/test_stage_ghidra.py`: `acquire`, `unpack`, `code` and `ghidra` through `cli.main` with fake adapters (`tests/fakes/fake_dump_script.py`, `tests/fakes/fake_ghidra.py`): `targets.tsv`, pass-through of `--skip-analysis`/`--filter`/`--limit`, recorded roots, and a missing `code` record or ABI mismatch failing with nothing recorded.
