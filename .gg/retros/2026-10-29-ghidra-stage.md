# Retro 2026-10-29: Ghidra stage (roadmap phase feffc3d0)

Scope: session | Kind: library/CLI + headless native-analysis automation
Evidence: conversation incl. compaction summary, git status, workspace/ghidra/0.4.6-17 logs, roadmap phase feffc3d0 (Done, rev 29). No earlier retros.

## What went well
- Real-data selection check (`$TEMP/zkcheck/check.py`) against dump.cs before the 69 min run caught the `$BurstDirectCallInitializer` leak cheaply. Confidence high.
- Resumable export: no-op `--skip-analysis` = "0 files to do" in ~90 s; deleting one .c rewrote only it, byte-identical. Confidence high.

## Timeline
1. Fixture missing ChatModal owner -> agent tests -> 1 iteration -> fixture fix.
2. Heredoc mangled adapter source -> agent -> ~3 iterations -> edit tool.
3. tuple+list, dict invariance -> pytest/pyright -> 2 iterations -> type fixes.
4. $BurstDirectCallInitializer leak -> throwaway check script -> 1 iteration -> skip list.
5. Full run silence wake at 600 s -> agent file check -> 0 (run was exporting).
6. 180 decompiler timeouts at 30 s only in script log -> USER asked to retry -> decompile_timeout option + 136 min retry -> 49 left.
7. Retry silent ~2 h -> agent polled ~12 times by counting files.
8. Doc numbers 373/5169 vs real 372/5166 -> agent after run -> hand fix.
9. Unused Path import -> ad-hoc ruff, not CI.
10. Exact info-dict assertion broke on new key -> pytest -> 1 iteration.

## Learnings
- Ghidra 12.2 requires JDK 25 (GettingStarted.md at Ghidra_12.2_build; run logged jdk 25.0.5+8). General. High.
- AndnixSH 3.2.1 il2cpp.h parses in 12.2 CParser with only typedef prelude + `: Base {` -> `Base super;` (0 ERROR (HeadlessAnalyzer), ~5 min). Local. High.
- Decompile time is heavy-tailed and the export pins one class file to one thread: 180/5166 timed out at 30 s, 49 at 300 s; GameServer.c ran alone ~60 of 136 retry minutes (Il2CppExport.java one task per file). Rejected "heap too small": java.exe 4.6 GB of 12 GB, errors are `process: timeout`. General. High.
- analyzeHeadless exits 0; export progress only every 100 files, so a 43-file retry printed nothing for ~2 h. General. High.
- Writing doc numbers before the real run forces hand-fixes (item 8). General. High.

## Gaps
- G1 export failures invisible to index.json/manifest (user-caught, item 6). Remediation: count `// decompilation failed` from .c files into index.json `failed` and manifest `functions_failed` (task af730946). S, general.
- G2 no progress during long export. Remediation: time-based progress line (e.g. every 60 s: files, functions, failed) in Il2CppExport.java. S, general.
- G3 one huge class file sets wall time. Remediation: split a file's functions across workers, join in RVA order before atomic rename (or largest-first). Verify with GameServer.c alone. M, general.
- G4 ruff/pyright not in CI or dev deps (ruff F401 caught ad hoc; CI runs only pytest; ruff format not adopted: 70 files would reformat). Remediation: add `ruff check` + `pyright` CI steps, pin in dev. S, local.
- G5 real-data selection audit thrown away ($TEMP/zkcheck/check.py). Remediation: `zk ghidra --dry-run` writes targets.tsv, prints roots and non-ZK classes, fails on a non-ZodiacKnights root. S, local.
- G6 doc numbers unchecked. Remediation: sequencing (write real-data numbers after the run). S, general.
Already tracked by audits: invalid --filter regex (4e32f4cd), decompile_timeout missing from manifest docs (45c11313).

## Sequencing fixes
- Run real data before writing "On 0.4.6-17..." doc numbers (item 8).
- Make retry knobs (timeouts) configurable before the first long run (item 6).

## Out of scope
- Heredoc escape mangling: agent tooling guidance.
- Silence wake can't tell busy from stalled: host tooling.

## Gap list
id | root cause | remediation | status
G1 | failure count stays in script log | count failures from .c into index.json + manifest | open (task af730946)
G2 | progress logged per 100 files only | time-based progress line in Il2CppExport.java | open
G3 | thread pool is per file | split functions of big files across workers, ordered join | open
G4 | CI runs only pytest | ruff check + pyright in CI, pinned dev deps | open
G5 | selection audit was a throwaway script | zk ghidra --dry-run with root check | open
G6 | docs written before real run | write real-data numbers after the run | open
