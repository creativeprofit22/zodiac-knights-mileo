# Format: `scripting_assemblies`

Module `zk/formats/scripting_assemblies.py`. A pure parser: text in, data out. It uses no tools and no workspace.

## Where it appears
`assets/bin/Data/ScriptingAssemblies.json`: the assemblies the player loads.

## Layout
```json
{"names": ["UnityEngine.CoreModule.dll", "ZodiacKnights.Game.dll", "..."], "types": [2, 16, "..."]}
```
`names[i]` has type `types[i]`. Type 2 is an engine module, and type 16 is a user or package assembly.

## API
```python
def parse(text: str) -> ScriptingAssemblies: ...  # ValueError on a bad shape or mismatched lengths
def game_assemblies(sa: ScriptingAssemblies) -> list[str]: ...
```
`game_assemblies` returns the sorted type-16 names without `.dll`, excluding names that start with Unity, System, Mono, mscorlib or netstandard.

## Evidence
The 0.4.6-17 APK lists `ZodiacKnights.Game.dll` and `ZodiacKnights.Logic.dll` as type 16, next to `Unity.*` and `System.*` package assemblies.

## Tests
`tests/test_formats.py` checks the game filter and that bad shapes raise `ValueError`.
