# Stage: `csharp`

`zk csharp [--abi ABI] [--input cpp2il|dummydll] [--force]`, module `zk/stages/csharp.py`

## Purpose
Produces a browsable C# project for each game assembly (namespaces, classes, fields, signatures, attributes, best-effort bodies), labelled as a reconstruction.

**IL2CPP never yields the original C#.** The game ships native code plus metadata. These projects rebuild declarations from that metadata, and method bodies are stubs or best-effort. Local names, inlined code and real logic are lost. **The Ghidra stage (the `ghidra` port) is the source of truth for logic.** Use this view to navigate types and signatures.

## Inputs
- Manifest `unpack` info: `il2cpp[abi]`, `metadata.path` and `assemblies.game` (the shared `stages/_unpack.py` lookup).
- Game fact `unity_version` (only for `--input cpp2il`).
- `--input dummydll`: `il2cpp/<v>/DummyDll/` from `zk code`. This stage does not import or run the code stage.
- Ports: [il2cpp_assemblies](../ports/il2cpp_assemblies.md) (only for `cpp2il`), [decompiler](../ports/decompiler.md) (v2).

## Outputs
- `csharp/<v>/assemblies/`: the il2cpp_assemblies contract (only for `cpp2il`; removed for `dummydll`).
- `csharp/<v>/projects/<Asm>/`: one C# project per game assembly.
- `csharp/<v>/report.json`: the [csharp_project](../formats/csharp_project.md) report, with `input` set.
- `csharp/<v>/README.md`: names the input used and states that this is a reconstruction.
- Manifest `csharp` info:

| key | meaning |
|---|---|
| `version`, `abi`, `input` | build label, ABI, and `cpp2il` or `dummydll` |
| `game_assemblies` | sorted `assemblies.game` from `unpack` |
| `assemblies` | il2cpp_assemblies adapter info (`tool`, `version`, `pin`, `dlls`…), or `null` for `dummydll` |
| `decompiler` | decompiler adapter info (`tool`, `version`, `exit_codes`, `decompile_errors`, `cs_files`); `decompile_errors` is `{<Asm>: n}`, the members ILSpy failed on (exit 70) |
| `report` | `{<Asm>: {types, methods, bodies}}` for each game assembly |
| `code_hash`, `adapters` | always recorded by the CLI |

## Arguments
| flag | default | meaning |
|---|---|---|
| `--abi` | the device ABI (`acquire` `abi`) if unpacked, else `arm64-v8a`, else the only unpacked ABI | which `libil2cpp.so` to read |
| `--input` | `cpp2il` | `cpp2il`: build assemblies from binary + metadata; `dummydll`: reuse `il2cpp/<v>/DummyDll/` |
| `--force` | off | delete `csharp/<v>/` and rerun |

## Failure modes
`RuntimeError` (exit 2), and nothing is recorded, when:
- there is no `unpack` record, or the ABI, metadata or game assemblies are missing (run `zk unpack`);
- `--input dummydll` is used without a `code` record for this version or without `il2cpp/<v>/DummyDll/` (run `zk code` first);
- `--input dummydll` is used with an `--abi` other than the one `zk code` dumped (rerun `zk code --abi <abi>` or pass that ABI);
- an adapter fails or leaves its contract incomplete (see `cpp2il.log` or `ilspycmd.log`);
- a game assembly has no `.csproj` in `projects/<Asm>/`, or no types in the report.

A low or zero `reconstructed` count is not a failure. Stub bodies are expected from metadata-only assemblies, and the report shows them honestly.

On this game (0.4.6-17) both inputs give 0 reconstructed bodies: every body is a stub (see [csharp_project](../formats/csharp_project.md#evidence)). With `--input dummydll`, ilspycmd also fails on 218 members of ZodiacKnights.Game ("Read out of bounds" in compiler-generated state machines). Their bodies hold ILSpy's error comment, and the count is in the manifest as `decompile_errors`. The C# view gives structure only: namespaces, types, fields, signatures and attributes. For logic, use the Ghidra stage.

## Tests
- `tests/test_stage_csharp.py` runs `acquire`, `unpack`, `code` and `csharp` through `cli.main` with fake adapters. It covers both inputs, a missing DummyDll, an ABI mismatch with `zk code`, a missing project, running before `unpack`, and the recorded info.
- `tests/test_csharp_adapters.py` covers the cpp2il and ilspycmd command lines, headless runs, failures and `report.json`, with an injected runner.
- `tests/test_csharp_project.py` covers the report parser.
