# Plan: Code dump stage (IL2CPP dump port, AndnixSH Il2CppDumper, Il2CppInspectorRedux cross-check, jadx)

## Audit (current state)
- Phase has no progress, blocker or verification recorded. Done so far: foundation, the `device_source` adapters, and the `acquire` and `unpack` stages (commit 0bec1a0). Nothing for this phase exists yet.
- `zk/ports/il2cpp_dump.py` is contract v1: `dump(binary, metadata, out) -> dict`, CONTRACT `dump.cs`, `script.json`, `DummyDll/`. It is missing `il2cpp.h` and the per-assembly summary, so the criteria need a contract change, and that needs an ADR.
- `zk/ports/decompiler.py` v1 (`decompile(apk, out)`, `sources/`) is already enough for jadx.
- `TOOLS` already pins jadx 1.5.6 with a sha256. There is no Il2CppDumper or Inspector entry.
- `zk.toml` has `il2cpp_dump` and `decompiler` commented out. `STAGE_MODULES = ("acquire", "unpack")`.
- `unpack` records `il2cpp[abi]` (path relative to `unpacked/<v>/`), `metadata.path`, `assemblies.game` (synthetic: `Assembly-CSharp`, `ZodiacKnights.Game`, `ZodiacKnights.Logic`) and the `metadata_version` fact.
- `tests/fakes/fake_dump_{a,b}.py` only meet contract v1, so they need updating.
- Release facts (GitHub API, checked today):
  - AndnixSH/Il2CppDumper 3.2.1 asset `Il2CppDumper-3.2.1-win-x64.zip`: sha256 `ff970e9fa3da75aaa37157c7ac669a6c022500a4c3903c966ba17a7b890160ce`.
  - LukeFZ/Il2CppInspectorRedux latest release is `2026.2`. Asset `Il2CppInspectorRedux.CLI-win-x64.zip`: sha256 `65c697bf79e03f1d530f98db5efd77b88831109cb7e91513bf132e56571358ef`. A `Legacy.CLI-win-x64` asset also exists; its digest gets read from the API if that CLI is the one chosen.

## Design decisions
1. **ADR 0003: `il2cpp_dump` contract v2 plus a new `il2cpp_crosscheck` port.**
   - The `il2cpp_dump` CONTRACT becomes `files=("dump.cs", "script.json", "il2cpp.h", "summary.json")`, `dirs=("DummyDll",)`. The Protocol is unchanged.
   - `summary.json` is the normalized "types and methods per assembly" summary: `{"assemblies": {"<Asm>": {"types": n, "methods": n, "classes": {"<Ns.Type>": method_count}}}}`, with sorted keys.
   - New port `il2cpp_crosscheck`, with Protocol `crosscheck(binary, metadata, out) -> dict` and CONTRACT `files=("summary.json",)`. It is a separate port so `[adapters]` keeps one adapter per port and the stage never names a tool.
   - `type_info` stays for a later phase. The ADR notes that `il2cpp.h` now also comes from the dumper.
2. **Docs filename**: keep `docs/ports/il2cpp_dump.md`, the same call the device_source phase made (it matches the port name and `index.md`). The criterion's `il2cpp-dump.md` is read as this page.
3. **Pure parsers in `zk/formats/`** (synthetic tests, no tools):
   - `il2cpp_script.py`: `validate(data: object) -> ScriptSummary`. It checks the top-level keys `ScriptMethod` (Address int, Name/Signature/TypeSignature str), `ScriptString` (Address int, Value str), `ScriptMetadata` (Address int, Name str, Signature str optional), `ScriptMetadataMethod` (Address int, Name str, MethodAddress int) and `Addresses` (list of int). It returns counts and raises `ValueError` with a JSON path on bad input.
   - `csharp_dump.py`: `summarize_dumper(text)` parses Il2CppDumper `dump.cs`, using the `// Image N: X.dll - <start>` header ranges, `// Namespace:` lines, `// TypeDefIndex: N` type lines and method lines inside `// Methods`. `summarize_inspector(files)` parses Inspector C# output in per-assembly layout. Both return the summary shape above. Nested-type names are normalized to `Outer.Inner`.
4. **Adapters** (each fetches its tool via `toolchain.path_of`; the process runner is injected for tests):
   - `adapters/il2cppdumper.py` (`PORT="il2cpp_dump"`): pure `command(exe, binary, metadata, out)` returns `[exe, binary, metadata, out, "--no-pause"]`. Runs with `stdin=DEVNULL` and captured output. It fails with a clear `RuntimeError` on a non-zero exit, on error/exception text in the output, or on a missing contract file. It then validates `script.json`, writes `summary.json`, and returns `{tool, version, summary totals, script counts}`.
   - `adapters/il2cppinspector.py` (`PORT="il2cpp_crosscheck"`): pure `command(...)` builds the Redux CLI call (binary, metadata, C# output per assembly). The exact flags and which CLI to use (new or Legacy) are checked from the downloaded tool's `--help` on Windows. Its output goes to `out/cs/`, then `summary.json`. The module docstring says it is AGPL-3.0, run only as an external download and never vendored.
   - `adapters/jadx.py` (`PORT="decompiler"`): pure `command(exe, apk, out)` returns `[exe, "-d", out/"sources", "--no-res", apk]`, using the apk that holds classes.dex. A non-zero exit is **recorded** (`exit_code`, last error lines) and does not fail the run. The run fails only if `sources/` is missing.
   - `TOOLS` gains `il2cppdumper 3.2.1` and `il2cppinspector 2026.2`, with the sha256 values above. The zip entry paths are confirmed by listing the downloaded zips.
5. **Stage `code`** (`zk/stages/code.py`, appended to `STAGE_MODULES`). Arguments: `--abi` (default `arm64-v8a`), `--force`, `--skip-crosscheck`, `--skip-java`.
   - Inputs come from the manifest's `unpack` info: the `il2cpp[abi]` binary and `metadata.path`. A missing input raises a `RuntimeError` saying to run `zk unpack`.
   - Steps: dump → `il2cpp/<v>/` and verify the contract. Every `assemblies.game` entry must appear in `summary.json` with types > 0 **and** as `DummyDll/<name>.dll`, otherwise `RuntimeError`. This covers ZodiacKnights.Game and ZodiacKnights.Logic without hard-coding them.
   - Cross-check → `il2cpp/<v>/crosscheck/`. A pure `compare(a, b, assemblies) -> dict` reports per game assembly `{types: [a, b], methods: [a, b], method_gaps: {class: [a, b]}}` and writes `il2cpp/<v>/crosscheck.json`. If any type count differs, it raises `RuntimeError` after writing the report.
   - jadx → `code/<v>/` and verify the contract.
   - Returns `{version, abi, dump: summary + counts, crosscheck: report, java: {exit_code, ...}}`.
6. `zk.toml`: `il2cpp_dump = "il2cppdumper"`, `il2cpp_crosscheck = "il2cppinspector"`, `decompiler = "jadx"`.

## Files
- New: `docs/adr/0003-il2cpp-dump-v2.md`, `docs/ports/il2cpp_crosscheck.md`, `docs/stages/code.md`, `src/zk/ports/il2cpp_crosscheck.py`, `src/zk/formats/il2cpp_script.py`, `src/zk/formats/csharp_dump.py`, `docs/formats/il2cpp_script.md`, `docs/formats/csharp_dump.md`, `src/zk/adapters/{il2cppdumper,il2cppinspector,jadx}.py`, `src/zk/stages/code.py`, `tests/fakes/fake_crosscheck.py`, `tests/test_il2cpp_script.py`, `tests/test_csharp_dump.py`, `tests/test_code_adapters.py`, `tests/test_stage_code.py`.
- Edit: `src/zk/ports/il2cpp_dump.py` (v2 contract), `src/zk/ports/__init__.py` (register the new port), `docs/ports/il2cpp_dump.md` and `docs/ports/decompiler.md` (contract, adapters table), `docs/architecture.md` and `docs/index.md` (data flow, new pages), `src/zk/core/toolchain.py` (TOOLS), `src/zk/stages/__init__.py`, `zk.toml`, `tests/fakes/fake_dump_{a,b}.py` (write `il2cpp.h`, `summary.json` and a valid `script.json`).
- `docs/stages/code.md` covers what IL2CPP recovers (types, fields and offsets, method signatures, RVAs/VAs, string literals, attributes, generic instances) and what it cannot (method bodies, local names, inlined or stripped code, shared generic bodies, const expressions). Bodies need Ghidra.

## Tests (offline, synthetic, CI on Linux)
- Command-line building for all three adapters, including `--no-pause` and `--no-res`. Il2CppDumper is called with `stdin=DEVNULL` (asserted through the injected runner).
- `script.json` schema: valid file passes; a missing key, wrong type and bad nested entry each fail with a path message.
- Parsers: a synthetic `dump.cs` with two images, nested types and methods gives the right summary. Same for synthetic Inspector files.
- jadx: a non-zero exit with `sources/` present is recorded and does not raise. A missing `sources/` raises.
- Il2CppDumper: an error in the output raises.
- Stage `code` run through `cli.main` with fake adapters on a synthetic unpack manifest:
  - records the summary and cross-check report;
  - a type-count mismatch exits 2 but `crosscheck.json` is still written;
  - a missing game assembly DLL exits 2;
  - **swapping fake_dump_a/fake_dump_b through config alone** changes the recorded `adapters.il2cpp_dump.module`.
- `test_boundaries` stays green (the stage imports no adapters or toolchain).

## Risks
- AndnixSH 3.2.1 was published yesterday. `--no-pause` support, the zip layout and the .NET runtime need are checked on first download. If the dumper fails on metadata v39, report `blocked` with the tool output.
- Il2CppInspectorRedux 2026.2 may not support metadata v39 or the per-assembly C# layout. If no pinned Redux release can read this build, that is a real blocker: the user must choose another cross-check tool or accept a gap.
- The two tools may count compiler-generated or nested types differently. The criterion requires identical type counts, so the normalization rules get documented, and any real difference is reported rather than hidden.
- A real run needs local game data (`raw/0.4.6-17/apk/base.apk`, present) and Windows. It runs through a gitignored `zk.local.toml` using the `folder` device_source. No game data or outputs are committed.

## Verification
- `python -m pytest -q` and `pyright` both green.
- Real run: `zk --config zk.local.toml acquire && zk ... unpack && zk ... code`. Check that the manifest `code` entry has a summary with ZodiacKnights.Game and ZodiacKnights.Logic, cross-check type counts that match, a list of method gaps, and the jadx exit code. Check that `il2cpp/<v>/DummyDll/ZodiacKnights.{Game,Logic}.dll` exist.

## Steps
1. Write ADR 0003, then update `zk/ports/il2cpp_dump.py` to contract v2, add `zk/ports/il2cpp_crosscheck.py`, and register it in `PORTS`.
2. Add `zk/formats/il2cpp_script.py` and `zk/formats/csharp_dump.py` with their format docs and synthetic tests.
3. Add the `il2cppdumper` and `il2cppinspector` `TOOLS` entries (sha256 pinned from the release digests) and confirm the zip entry paths by downloading with `zk tools`.
4. Implement `zk/adapters/il2cppdumper.py`, `zk/adapters/il2cppinspector.py` and `zk/adapters/jadx.py`, each with a pure `command()` builder and an injected runner, plus `tests/test_code_adapters.py`.
5. Implement `zk/stages/code.py` with `compare()`, the game-assembly check and the cross-check report, then append it to `STAGE_MODULES`.
6. Update the fakes, add `tests/fakes/fake_crosscheck.py` and `tests/test_stage_code.py`, including config-only adapter swapping.
7. Set the three adapters in `zk.toml`. Write `docs/stages/code.md` and update `docs/ports/il2cpp_dump.md`, `docs/ports/decompiler.md`, the new port page, `docs/architecture.md` and `docs/index.md`.
8. Run `python -m pytest -q` and `pyright` and fix any failures.
9. Do the real run on Windows against `raw/0.4.6-17` through a gitignored `zk.local.toml`. Fix parser normalization against the real outputs, record the results, and report progress with `roadmap_status`.
