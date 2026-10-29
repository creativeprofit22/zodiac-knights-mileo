# Port: `decompiler` (contract v2)

Module `zk/ports/decompiler.py`. Changing this contract needs a new ADR. v2 comes from [ADR 0004](../adr/0004-decompiler-v2.md). v1 (the Java decompiler) is now [java_decompiler](java_decompiler.md).

Decompiles .NET assemblies into one C# project per game assembly, plus a report. The assemblies come from an IL2CPP build in one of two ways: built from the game binary + `global-metadata.dat` by the [il2cpp_assemblies](il2cpp_assemblies.md) port, or taken from the il2cpp_dump `DummyDll/` folder. The `csharp` stage records which one it used.

## Protocol
```python
class Decompiler(Protocol):
    def decompile(self, assemblies: Path, names: list[str], out: Path) -> dict: ...
```
`assemblies/<name>.dll` must exist for each name. The other DLLs in `assemblies/` are references.

## Artifact contract
| path | kind | content |
|---|---|---|
| `projects/` | folder | `projects/<name>/`: a C# project (`.csproj` + `.cs`) for each name |
| `report.json` | file | [csharp_project](../formats/csharp_project.md) report: per-assembly types, methods, and stub/reconstructed/none bodies |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| `ilspycmd` | ilspycmd 11.2.0.10050, native AOT win-x64 (NuGet `ilspycmd.win-x64`), `-p -o projects/<name> -r <assemblies> --disable-updatecheck <name>.dll` | default |

## Notes
- The ILSpy GitHub release has no ilspycmd asset. The pin is the NuGet package, which is a zip holding `tools/any/win-x64/ilspycmd.exe`.
- ilspycmd runs headless with stdin closed, once per assembly. Output goes to `ilspycmd.log`. Exit 70 with ILSpy's "N error(s) occurred" summary is a partial run: the project is kept, the failed bodies hold ILSpy's error comment (counted as `stub`), and the count is recorded as `decompile_errors`. Any other non-zero exit, or a missing project folder, raises `RuntimeError`.
- The adapter writes `report.json` with `input: null`. The stage fills it in (`cpp2il` or `dummydll`).
