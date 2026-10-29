# Stage: `<name>`

`zk <name> [args]`, module `zk/stages/<name>.py`

`<name>` must be unique and not `game` (manifest key for game facts), `status` or `tools` (built-in subcommands).

## Purpose
One sentence: what this stage produces and why.

## Inputs
- Workspace areas or files read, e.g. `unpacked/<v>/…`
- Game facts read from `manifest["game"]`
- Ports used, e.g. `il2cpp_dump`, never a tool name

## Outputs
- Workspace area written, e.g. `il2cpp/<v>/`
- Manifest info keys, plus `code_hash` and `adapters`, which are always recorded
- Game facts recorded, if any

## Arguments
| flag | default | meaning |
|---|---|---|

## Failure modes
What raises `RuntimeError` (exit 2) and how to fix it.

## Tests
Which tests cover it and which synthetic data they use.
