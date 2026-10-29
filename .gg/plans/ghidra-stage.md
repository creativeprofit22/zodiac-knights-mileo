# Plan: `zk ghidra` — headless Ghidra 12.2 on the il2cpp_dump contract

Roadmap phase `feffc3d0…` (status: planning, no progress recorded). Nothing Ghidra-related exists yet beyond the
`ghidra` port v1 stub (`analyze(binary, dump_dir, out)`, contract `index.json` + `functions/`), an unpinned-in-zk.toml
`# ghidra = "ghidra"` line, and a `ghidra` 12.1.4 entry in `TOOLS` (no adapter uses it).

## Findings that shape the plan

- **Ghidra 12.2 needs JDK 25**, not 21 (GettingStarted.md at `Ghidra_12.2_build`: "Java 25 64-bit JDK").
  Release asset `ghidra_12.2_PUBLIC_20261016.zip`, GitHub digest `sha256:2c2cd776…7be67` (matches the phase).
  Temurin 25.0.5+8 Windows x64 zip: `OpenJDK25U-jdk_x64_windows_hotspot_25.0.5_8.zip`,
  Adoptium checksum `636bdc13dc649ddc7d5921c5c7d23cca6e44fd19d662b45cc9c02135a6c96c42` (re-check against the
  GitHub asset digest before pinning). `jdk21` stays: jadx uses it via `java_env`.
- **SSA's class index reads dump.cs**; the phase allows only `script.json` + `il2cpp.h`. Replacement: the set of
  type owners = `strip_generics(Name.split("$$")[0])` of every `ScriptMethod` ∪ `ScriptMetadata` `*_TypeInfo` names
  (arrays `[]` skipped). A method's class = the **shortest** owner prefix (namespaces never own methods), so
  `ZodiacKnights.Game.AdminLiveOps.<AuthenticateCo>d__54$$MoveNext` → (`ZodiacKnights.Game`, `AdminLiveOps`), and
  global nested `ChatModal.ChatEntry` → (`""`, `ChatModal`).
- **This build's namespaces** (dump.cs, 0.4.6-17): roots `UnityEngine` (incl. `UnityEngine.InputSystem`,
  `.Rendering`, `.UIElements`, `.TextCore`), `System`, `ZodiacKnights` (`.Game` 270, `.Logic` 119), `Unity`
  (`.Collections`, `.Burst`, `.Mathematics`, `.RenderPipelines`, `.Properties`, `.Jobs`…), `Mono`, `Microsoft`,
  `UnityEngineInternal`, `Internal`, `JetBrains`, `AOT`; global-namespace method owners are all engine/BCL:
  `Interop`, `InteropErrorExtensions`, `SR`, `Locale`, `UISupport`, `UnitySourceGeneratedAssemblyMonoScriptTypes_v1`,
  `OnTilePostProcess*`, `RenderGraphCompilationCache`, `FullScreenPassRendererFeature_OldGUID`,
  `__JobReflectionRegistrationOutput__*`. No TMPro/Firebase/Google/Kotlin here, but they go in the list anyway.
- **il2cpp.h** (AndnixSH 3.2.1, 70 MB): 4133 `struct X : Base {` inheritance lines (SSA fix-up handles them); no
  `#`, `__attribute__` or `alignas`. Whether Ghidra 12.2's CParser accepts the rest is only knowable by running it.
- `core/codehash.py` hashes only `*.py`, so package-shipped `.java` scripts would not change `code_hash`.
- Stages may not import adapters or `zk.core.toolchain` (test_boundaries), so headless/JDK logic goes in the adapter.

## Design

Port `ghidra` **contract v2** (new ADR 0005), because the run needs a target list and `--skip-analysis`:

```python
class Ghidra(Protocol):
    def analyze(self, binary: Path, dump_dir: Path, targets: Path, out: Path, skip_analysis: bool) -> dict: ...
CONTRACT = ArtifactContract("ghidra", files=("index.json",), dirs=("functions", "project"))
```
- `dump_dir` is the il2cpp_dump output; the adapter reads only `script.json` and `il2cpp.h` from it.
- `targets` is a TSV `rva_hex \t <Ns>/<Class>.c` written by the stage.
- Adapter writes `project/libil2cpp.gpr`, `functions/<Ns>/<Class>.c`, logs, and
  `index.json` = `{tool, version, jdk, project, classes: {relpath: functions}, missing: [relpaths not written]}`.

Files:
- `src/zk/formats/il2cpp_script.py`: add `strip_generics`, `type_owners(data) -> frozenset[str]`,
  `resolve_class(method_name, owners) -> tuple[str, str] | None` (pure, typed).
- `src/zk/stages/ghidra.py` (new): `NAME="ghidra"`, args `--abi`, `--skip-analysis`, `--filter`, `--limit`,
  `--force`; `THIRD_PARTY` roots (UnityEngine, UnityEngineInternal, Unity, System, Mono, Microsoft, Internal,
  JetBrains, AOT, Interop, TMPro, Firebase, Google, Kotlin, kotlin, Newtonsoft); `THIRD_PARTY_GLOBAL` prefixes (list
  above); `is_game_class`, `class_relpath`, `select_targets(methods, owners, pattern, limit)`. `execute`: needs a
  `code` record for this version with the same ABI (as csharp does), `il2cpp_dump` contract verified on
  `il2cpp/<v>/`, validates script.json with `il2cpp_script.validate`, writes `ghidra/<v>/targets.tsv`, calls the
  port, verifies the contract, records `{version, abi, skip_analysis, classes_targeted, functions_targeted, roots
  (exported root namespaces → class counts), analysis: adapter info}`. `--force` deletes `ghidra/<v>/`.
- `src/zk/adapters/ghidra/__init__.py` (new package): `PORT`, `create(cfg)` (reads `[options.ghidra] maxmem`,
  default `12G`), pure `symbol_lines`, `ghidra_header` (SSA prelude + `: Base {` → `{ Base super;`, plus any fix-up
  the real run proves necessary), `headless_cmd`, `headless_errors`, `run_lines`, `run_logs`, `ghidra_env`,
  `pin_jdk`; class `GhidraHeadless(tools, run, locate)` with `analyze`. It removes stale `*.part` files, refuses
  `skip_analysis` without `project/libil2cpp.gpr`, runs analyzeHeadless with `stdin=DEVNULL`, fails on any
  `ERROR (HeadlessAnalyzer)` line from this run (exit code is 0 even on failed import), then writes `index.json`.
- `src/zk/adapters/ghidra/scripts/Il2CppImport.java`, `Il2CppExport.java`: ported from SSA 6e1be49 (`@category zk`).
  Import change: after `CParser.parse`, fail the script (throw) when `parser.didParseSucceed()` is false and print
  `parser.getParseMessages()`, so a header parse error surfaces as `ERROR (HeadlessAnalyzer) REPORT SCRIPT ERROR`
  and fails the stage. Keep SLOW_ANALYZERS incl. "Call Convention ID" and "Decompiler Switch Analysis".
- `src/zk/core/toolchain.py`: `ghidra` → 12.2 (url, entry `ghidra_12.2_PUBLIC/support/analyzeHeadless.bat`, sha256
  from the phase); add `jdk25` 25.0.5+8; fix the "Ghidra 12 needs JDK 21" comment (jdk21 = jadx).
- `src/zk/core/codehash.py`: hash `*.py` and `*.java` in package folders.
- `src/zk/ports/ghidra.py` → v2; `src/zk/stages/__init__.py` append `"ghidra"`; `zk.toml` `ghidra = "ghidra"`;
  `pyproject.toml` `[tool.setuptools.package-data] "zk.adapters.ghidra" = ["scripts/*.java"]`.
- Docs: `docs/adr/0005-ghidra-v2.md`, `docs/ports/ghidra.md` (v2, adapter row), `docs/stages/ghidra.md` (from
  template; GUI: set `JAVA_HOME` to tools/jdk25…, `ghidraRun.bat`, open `workspace/ghidra/<v>/project/libil2cpp.gpr`,
  answer No to re-analysis, project locked during headless runs; optional GhidraMCP (Apache-2.0): install a release
  built for 12.2 via File > Install Extensions, enable GhidraMCPPlugin, run `bridge_mcp_ghidra.py`; 12.x support
  unverified), `docs/formats/il2cpp_script.md` (class resolution API), `docs/architecture.md` + `docs/index.md` links.

## Tests (offline, synthetic)
- `tests/test_il2cpp_script.py`: owners/resolve for nested compiler-generated, generic, global-nested, TypeInfo-only
  and unknown names.
- `tests/test_ghidra.py`: select_targets keeps only ZodiacKnights among UnityEngine.InputSystem, Unity.Burst,
  Unity.RenderPipelines.Universal, Unity.Collections, Unity.Mathematics, TMPro, System, Mono, Firebase, Google,
  Kotlin and global `SR`/`__JobReflectionRegistrationOutput__…`; filter/limit; class_relpath; symbol_lines;
  ghidra_header (and any added fix-up); headless_cmd both modes; headless_errors; run_lines; run_logs; ghidra_env;
  pin_jdk on a tmp launch.properties; adapter `analyze` with an injected runner (success → index.json + contract;
  `ERROR (HeadlessAnalyzer)` → RuntimeError; skip_analysis without project → RuntimeError); pins (ghidra 12.2 sha,
  jdk25 sha present); scripts ship in the package.
- `tests/test_stage_ghidra.py` + `tests/fakes/fake_ghidra.py`: via `cli.main` after acquire/unpack/code with a fake
  dump that writes a synthetic script.json: targets.tsv content, `--skip-analysis` passed through, roots recorded,
  missing `code` record / ABI mismatch fail with nothing recorded.
- `tests/test_codehash.py`: a `.java` file in a package adapter changes the hash.

## Risks
- CParser may reject parts of the Unity 6 header → extend `ghidra_header` with a targeted, tested fix-up and
  document it in docs/stages/ghidra.md; if unfixable in this phase, report blocked.
- Analyzer names may have changed in 12.2 → script log shows "analyzer option not found"; update the list.
- Full analysis is long (SSA: hours before disabling analyzers) and needs ~12 GB heap; run it in the background.
- Downloads: Ghidra ~570 MB, JDK 25 ~141 MB into `tools/` (gitignored).
- Shortest-owner rule could mis-split if a namespace equals a type name; checked against dump.cs on real data.

## Verification
- `python -m pytest -q` and `pyright` green.
- One-off real-data check (not committed): the script.json class resolution agrees with dump.cs namespaces for every
  ZodiacKnights method owner, and selected roots are exactly `{"ZodiacKnights"}`.
- `zk ghidra` on 0.4.6-17: no `ERROR (HeadlessAnalyzer)`; script log shows header parsed, named/signature counts,
  no "analyzer option not found"; `functions/ZodiacKnights.Game/*.c` present.
- `zk ghidra --skip-analysis`: re-export from the saved project skips existing files (resumable); deleting one .c
  and rerunning rewrites only that file.

## Steps
1. Re-check the Temurin 25.0.5+8 Windows x64 zip digest on its GitHub release asset, then update `TOOLS` in `src/zk/core/toolchain.py` (ghidra 12.2 url/entry/sha256, new jdk25, comment fix) and extend `test_toolchain.py` pins.
2. Make `core/codehash.py` include `*.java` in package folders and add a test in `tests/test_codehash.py`.
3. Add `strip_generics`, `type_owners`, `resolve_class` to `src/zk/formats/il2cpp_script.py` with tests in `tests/test_il2cpp_script.py`.
4. Write ADR 0005 and change `src/zk/ports/ghidra.py` to contract v2 (`analyze(binary, dump_dir, targets, out, skip_analysis)`, dirs `functions`, `project`); update `docs/ports/ghidra.md`.
5. Create `src/zk/adapters/ghidra/__init__.py` (pure helpers, `GhidraHeadless.analyze`, `create`) and port `scripts/Il2CppImport.java` (with parse-failure check) and `scripts/Il2CppExport.java` from SSA 6e1be49; add package-data to `pyproject.toml`.
6. Create `src/zk/stages/ghidra.py` with the rebuilt skip lists, target selection and `execute`; append `"ghidra"` to `STAGE_MODULES`; set `ghidra = "ghidra"` in `zk.toml`.
7. Add `tests/test_ghidra.py`, `tests/fakes/fake_ghidra.py` and `tests/test_stage_ghidra.py`; run `python -m pytest -q` and `pyright` until green.
8. Run the one-off real-data check of class resolution vs dump.cs and of selected roots; adjust the skip lists if anything non-ZodiacKnights remains.
9. Run `zk ghidra` on 0.4.6-17 in the background; inspect headless and script logs for header parse errors and missing analyzer names; add a tested `ghidra_header` fix-up or analyzer-list update if needed and rerun.
10. Run `zk ghidra --skip-analysis` twice (second run skips everything; then delete one .c and confirm only it is rewritten).
11. Write `docs/stages/ghidra.md` (inputs, outputs, args, failures, header fix-ups, GUI opening with JDK 25, optional GhidraMCP) and update `docs/formats/il2cpp_script.md`, `docs/architecture.md` and `docs/index.md`.
12. Run the full test suite and pyright once more, then report progress with `roadmap_status` (done only if every criterion is verified).
