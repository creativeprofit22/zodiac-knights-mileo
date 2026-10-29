# Stage: `code`

`zk code [--abi ABI] [--force] [--skip-crosscheck] [--skip-java]`, module `zk/stages/code.py`

## Purpose
Recovers the game's C# types and method signatures from the IL2CPP build, checks them with a second, independent dumper, and decompiles the Java/Kotlin layer of the APK.

## Inputs
- Manifest `unpack` info (written by `zk unpack`): `il2cpp[abi]`, `metadata.path` and `assemblies.game`. Paths are relative to `unpacked/<version>/`.
- `raw/<version>/apk/*.apk`: the APK whose unpacked folder holds `classes.dex`, otherwise `base.apk`.
- Ports: [il2cpp_dump](../ports/il2cpp_dump.md) (v2), [il2cpp_crosscheck](../ports/il2cpp_crosscheck.md), [decompiler](../ports/decompiler.md).

## Outputs
- `il2cpp/<version>/`: the il2cpp_dump contract (`dump.cs`, `script.json`, `il2cpp.h`, `summary.json`, `DummyDll/`).
- `il2cpp/<version>/crosscheck/`: the il2cpp_crosscheck contract (`summary.json`, plus the tool's own output).
- `il2cpp/<version>/crosscheck.json`: the comparison report. It is written before the type check, so it exists even when the stage fails.
- `code/<version>/`: the decompiler contract (`sources/`).
- Manifest `code` info:

| key | meaning |
|---|---|
| `version`, `abi` | build label and dumped ABI |
| `game_assemblies` | sorted `assemblies.game` from `unpack` |
| `dump` | adapter info plus `assemblies: {name: {types, methods}}` for each game assembly |
| `crosscheck` | `{types_match, assemblies, method_gap_classes}`, or `null` with `--skip-crosscheck`. `assemblies[name]` is `{types, methods, method_gaps}`, each value a `[dump, crosscheck]` pair; `method_gaps` lists only classes whose method counts differ. |
| `java` | `{apk, exit_code, errors, java_files, ...}` from the decompiler, or `null` with `--skip-java` |
| `code_hash`, `adapters` | always recorded by the CLI |

## What IL2CPP recovers, and what it cannot
- Recovered from `global-metadata.dat` + `libil2cpp.so`: type names and namespaces, nesting, base types and interfaces, fields with offsets, method signatures, method RVAs/VAs, string literals, custom attributes and the generic instances that were compiled.
- Not recoverable by a dumper: method bodies (only native code exists), local variable names, code that was inlined or stripped, the bodies of shared generic methods, and const expressions (only their values). Reading method bodies needs the native code in Ghidra (the `ghidra` port), using `script.json` and `il2cpp.h` to name functions and types.

## Arguments
| flag | default | meaning |
|---|---|---|
| `--abi` | `arm64-v8a` | which `libil2cpp.so` to dump |
| `--force` | off | delete `il2cpp/<v>/` and `code/<v>/` and rerun every step |
| `--skip-crosscheck` | off | do not run `il2cpp_crosscheck` |
| `--skip-java` | off | do not run `decompiler` |

## Failure modes
- `RuntimeError` (exit code 2), and nothing is recorded:
  - there is no `unpack` record for the current version, the ABI has no `libil2cpp.so`, `global-metadata.dat` is missing, or no game assemblies were found (run `zk unpack`, or pass `--abi`);
  - an adapter fails or leaves its artifact contract incomplete;
  - a game assembly has no types in `summary.json` or no `DummyDll/<name>.dll`;
  - type counts differ between the two dumpers for any game assembly. Read `crosscheck.json` to see where.
- Recorded without failing:
  - method count differences per class (`method_gaps`);
  - a non-zero decompiler exit code, as long as `sources/` exists.

## Tests
- `tests/test_stage_code.py` runs `acquire`, `unpack` and `code` through `cli.main` with fake adapters on a synthetic APK. It covers `compare`, the recorded info, a type mismatch (exit 2 with `crosscheck.json` written), a missing game DLL, swapping the dump adapter through `zk.toml` alone, and running before `unpack`.
- `tests/test_code_adapters.py` covers the real adapters' command lines and failure handling with an injected runner.
