# Format: `csharp_dump_diff`

Module `zk/formats/csharp_dump_diff.py`. Pure data in, data out: it compares two [csharp_dump](csharp_dump.md) summaries. It uses no tools and no workspace.

## Where it appears
- `il2cpp/<v>/crosscheck.json` (`zk code`): `compare` of the il2cpp_dump and il2cpp_crosscheck `summary.json` for the game assemblies.
- `assets/<v>/report.json` `crosscheck` (`zk assets`): `tag_used` over `compare` for the assemblies MonoBehaviours use.

## Layout
`compare` returns `{"assemblies": {name: {"types": [a, b], "methods": [a, b], "method_gaps": {class: [a, b]}}}, "type_mismatches": [...], "types_match": bool}`. A side missing an assembly or class counts as `null`.

`tag_used` returns `{"assemblies": {name: {"types", "methods", "differences": {class: {"counts", "used", "rule"}}, "used_classes", "type_count_residual", "unexplained": [...]}}, "unexplained": n}`. A used class that differs with no matching rule is unexplained, and so is a type-count gap that one-sided classes do not account for.

## API
```python
def compare(a: dict, b: dict, assemblies: Iterable[str]) -> dict: ...
def tag_used(diff: dict, used: Mapping[str, Iterable[str]], rules: Mapping[str, str] | None = None) -> dict: ...
```

## Evidence
Moved out of the assets stage so `code` and `assets` share it without one stage importing another's private module.

## Tests
`tests/test_assets_compare.py` and `tests/test_stage_code.py` use synthetic summaries.
