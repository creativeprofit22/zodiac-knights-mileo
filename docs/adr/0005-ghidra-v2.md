# ADR 0005: `ghidra` contract v2 (targets, saved project, re-export)

Status: accepted (amends the `ghidra` part of ADR 0001)

## Context

ADR 0001 sketched the `ghidra` port as `analyze(binary, dump_dir, out)` with `index.json` + `functions/`. The real stage (ported from SSA) analyses `libil2cpp.so` once, a run of hours, and exports decompiled C only for the game's own classes. Choosing those classes is pipeline policy, not tool knowledge, and re-exporting without re-analysing needs the saved project and a flag.

## Decision

- `ghidra` becomes contract v2: `analyze(binary, dump_dir, targets, out, skip_analysis) -> dict`, `files=("index.json",)`, `dirs=("functions", "project")`.
- `dump_dir` is the `il2cpp_dump` output; the adapter reads only `script.json` and `il2cpp.h` from it and never runs the dumper.
- `targets` is a TSV written by the stage: `rva_hex<TAB><Ns>/<Class>.c`, one line per function to export.
- The adapter keeps the analysed project in `project/`, writes `functions/<Ns>/<Class>.c` resumably (existing files are kept), and writes `index.json` = `{tool, version, jdk, project, classes: {relpath: functions}, missing: [relpaths], failed: {relpath: functions not decompiled}}` (`failed` added later, additive).
- `skip_analysis=True` re-exports from `project/`; the adapter fails if no saved project exists.

## Consequences

- The `ghidra` stage owns the third-party skip list and class resolution (from `script.json`, via `zk.formats.il2cpp_script`); the adapter knows only Ghidra.
- No adapter implemented v1, so nothing needs migrating.
