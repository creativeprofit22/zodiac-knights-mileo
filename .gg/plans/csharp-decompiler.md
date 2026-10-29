# Plan: readable C# view (Cpp2IL + ilspycmd)

Phase 972b9b21. Nothing from this phase exists yet. `decompiler` is currently the jadx/Java port.
User decisions: (1) ADR 0004 renames the Java port to `java_decompiler` and makes `decompiler` v2 the C# port; (2) two ports: `il2cpp_assemblies` (Cpp2IL) and `decompiler` (ilspycmd).

## Design

### Ports (ADR 0004)
- `java_decompiler` (contract v1, same as today's decompiler): `decompile(apk, out) -> dict`, `dirs=("sources",)`. jadx moves here.
- `il2cpp_assemblies` (new, v1): `build(binary, metadata, unity_version, out) -> dict`, `dirs=("assemblies",)`. One `<Asm>.dll` per assembly.
- `decompiler` (v2): `decompile(assemblies: Path, names: list[str], out: Path) -> dict`, `files=("report.json",)`, `dirs=("projects",)`. Writes `projects/<Asm>/` (a C# project per assembly) and `report.json`.
- Changes: `src/zk/ports/{java_decompiler,il2cpp_assemblies,decompiler}.py` and the `PORTS` registry. `zk.toml` gets `java_decompiler = "jadx"`, `il2cpp_assemblies = "cpp2il"`, `decompiler = "ilspycmd"`. The code stage, `tests/fakes/fake_decompiler.py` (renamed `fake_java_decompiler.py`), `tests/test_stage_code.py`, `tests/test_contracts.py` and `docs/stages/code.md` switch to `java_decompiler`. The manifest key changes after the next `zk code` run.

### Report format (`zk/formats/csharp_project.py`, pure)
- `summarize(files: dict[str, str]) -> dict`: per assembly `{"types", "methods", "bodies": {"stub", "reconstructed", "none"}}`, with keys sorted.
- A body counts as a stub when it is empty or holds only `throw null;`, `throw new NotImplementedException(...)`, `return default...;`, or Cpp2IL's stub marker (the exact text is taken from the real output during implementation). Any other body counts as reconstructed. Abstract, extern and interface members count as `none`.
- `report.json` is `{"input": "cpp2il"|"dummydll", "tool": ..., "assemblies": {Asm: {...}}, "disclaimer": "..."}`.

### Adapters
- `zk/adapters/cpp2il.py` (`PORT="il2cpp_assemblies"`): `command(exe, binary, metadata, unity_version, out)` → `--force-binary-path`, `--force-metadata-path`, `--force-unity-version`, `--output-as dummydll`, `--output-to <out>/assemblies`. The flags are checked against `--help` of the pinned build. It uses an injected runner, closes stdin, writes `cpp2il.log`, and fails on a non-zero exit or a missing `assemblies/`. It returns the tool, version, pin (release tag or commit sha) and the DLL count.
- `zk/adapters/ilspycmd.py` (`PORT="decompiler"`): for each name, `command(exe, dll, refdir, outdir)` → `[exe, "-p", "-o", outdir, "-r", refdir, dll]` (`-r` is checked in the 11.2 source or help). It runs headless with stdin closed, then reads every `projects/<Asm>/**/*.cs` and writes `report.json`.
- `toolchain.TOOLS` gets:
  - `cpp2il` `2022.1.0-pre-release.21`, the Windows asset (kind `file` if it is a single exe);
  - `ilspycmd` `11.2`, the native AOT win-x64 zip.
  - Both sha256 values come from GitHub release digests (`gh release view --json assets`).
- Fallback, only if pre-release.21 fails on metadata v39: add a pinned Cpp2IL source archive at a fixed development sha (`archive/<sha>.zip`) and a pinned portable .NET SDK. Add `cpp2il_build(tools)` in the adapter that runs `dotnet publish` once into `tools/cpp2il-<sha>/`. Record the sha as the version, and note it in the docs.

### Stage `csharp` (`zk/stages/csharp.py`, appended to `STAGE_MODULES`)
- `zk csharp [--abi arm64-v8a] [--input cpp2il|dummydll] [--force]`.
- Inputs come from the `unpack` record (binary, metadata, game assemblies) and the `unity_version` fact. The shared lookup moves into `zk/stages/_unpack.py`, which code.py also uses (no code-stage import). With `--input dummydll` it uses `il2cpp/<v>/DummyDll/` and fails clearly if that is missing ("run `zk code`").
- The output area is new: `csharp/<v>/` (added to `STAGE_DIRS`). It holds `assemblies/` (cpp2il input only), `projects/`, `report.json` and `README.md`. The README states the input used and that this is a reconstruction, not the original C#.
- The stage checks `projects/<Asm>/` has a `.csproj` and at least one type for each game assembly; otherwise it raises `RuntimeError`.
- Manifest info: `version`, `abi`, `input`, `game_assemblies`, `assemblies` (adapter info), `report` (per-assembly counts).

### Docs
- `docs/adr/0004-decompiler-v2.md`.
- `docs/ports/decompiler.md` (rewritten, v2; input is binary+metadata via `il2cpp_assemblies`, or DummyDll assemblies).
- New: `docs/ports/java_decompiler.md`, `docs/ports/il2cpp_assemblies.md`, `docs/formats/csharp_project.md`, `docs/stages/csharp.md`.
- `docs/stages/csharp.md` says plainly that IL2CPP never yields the original C#, that bodies are stubs or best-effort, and that the Ghidra stage is the source of truth for logic.
- Update `docs/architecture.md` (data flow, the `csharp` area) and `docs/index.md`.

## Risks
- Cpp2IL pre-release.21 may reject metadata v39 or mis-read parameter indexes. Check the real run's type counts against `code.dump.assemblies` (1153 / 202). If it fails, use the fallback build.
- Cpp2IL dummydll bodies are likely all stubs, so `reconstructed` may be 0. That is reported honestly, not hidden.
- The `-r`/flag names are unverified until checked in the help output or source.
- The rename breaks existing `zk.toml` files that use `decompiler = "jadx"`. Config validation gives a clear error (jadx's PORT mismatch).

## Verification
- `python -m pytest -q` and `pyright`.
- Real run: `zk tools cpp2il ilspycmd`, `zk csharp`, then `zk csharp --input dummydll --force`. Confirm v39 loads, the projects exist for both ZodiacKnights assemblies, and the report counts are sane. Then `zk code --skip-crosscheck --force` to confirm the jadx rename works.

## Steps
1. Write `docs/adr/0004-decompiler-v2.md`. Add `zk/ports/java_decompiler.py` and `zk/ports/il2cpp_assemblies.py`, rewrite `zk/ports/decompiler.py` as v2 and register all three in `PORTS`.
2. Switch jadx, the code stage, the fakes, the tests, `zk.toml` and `docs/stages/code.md` to `java_decompiler`. Add `docs/ports/java_decompiler.md`.
3. Extract the unpack-input lookup into `zk/stages/_unpack.py` and use it from `code.py`.
4. Add `zk/formats/csharp_project.py` with `summarize`, and `tests/test_csharp_project.py` on synthetic C# (stub, reconstructed and abstract bodies; nested and generic types).
5. Look up the Cpp2IL pre-release.21 and ILSpy 11.2 asset names and sha256 digests with `gh release view`, and add both `TOOLS` entries.
6. Add `zk/adapters/cpp2il.py` and `zk/adapters/ilspycmd.py` with `command()` builders and injected runner, locate and env.
7. Add `tests/test_csharp_adapters.py`. It covers the command lines, stdin closed, failure on a non-zero exit or missing output, report.json written from synthetic project files, and Protocol conformance.
8. Add `workspace` area `csharp`, `zk/stages/csharp.py` (in `STAGE_MODULES`) with the `--input`, `--abi` and `--force` flags, the README label and the per-assembly checks. Add fake adapters and `tests/test_stage_csharp.py` (both inputs, a missing DummyDll, a missing project, the recorded info).
9. Write `docs/ports/decompiler.md` (v2), `docs/ports/il2cpp_assemblies.md`, `docs/formats/csharp_project.md` and `docs/stages/csharp.md`, and update `docs/architecture.md` and `docs/index.md`.
10. Run `python -m pytest -q` and `pyright`, then fix any failures.
11. Run `zk tools cpp2il ilspycmd` and `zk csharp` on the real game. If Cpp2IL fails on v39, add the pinned-sha source build fallback, re-run it, and record the sha in TOOLS and the docs. Pin the real stub marker in the parser and tests.
12. Run `zk csharp --input dummydll --force` and `zk code --skip-crosscheck --force`. Check that both ZodiacKnights projects and the report counts exist, then report the phase status through `roadmap_status` with evidence.
