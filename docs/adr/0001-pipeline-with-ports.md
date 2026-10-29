# ADR 0001: Stage pipeline with ports at tool boundaries

Status: accepted

## Context

The work turns an APK into readable code, types and data. This takes a chain of steps: pull, unpack, IL2CPP dump, decompile, type info, Ghidra analysis, then format parsing. Every step but parsing wraps a third-party tool, and these tools break against new game builds. For example, Perfare's Il2CppDumper fails on IL2CPP metadata v39, which this game ships. The previous project (SSA) used a plain stage pipeline with tools called directly inside stages, so replacing a tool meant editing the stage.

## Decision

- Keep SSA's **stage pipeline**: stages share only the workspace folders and `manifest.json`. Workspace, manifest and toolchain code are copied from SSA, not imported.
- Put a **port** at each external-tool boundary. A port is a `runtime_checkable` Protocol plus an `ArtifactContract`, which lists the files and folders the adapter must leave. The first ports are `device_source`, `il2cpp_dump`, `decompiler`, `type_info` and `ghidra`, all at contract v1.
- `zk.toml` `[adapters]` picks **one adapter per port**. Stages call `ctx.adapter(port)` and never name a tool.
- **Dependency rule**: `zk.core`, `zk.formats` and `zk.ports` import nothing from `zk.stages` or `zk.adapters`. Stages depend only on port Protocols and artifact contracts, never on a concrete adapter or `zk.core.toolchain`. Adapters never import stages. `tests/test_boundaries.py` enforces this.

## Rejected: full hexagonal architecture

We rejected a domain core with ports for everything: filesystem, manifest, logging, config. The domain here is thin. It is mostly "run a tool, check its output, parse bytes", so wrapping the workspace in more abstraction adds code and costs nothing in safety. The real risk is external tools breaking or being replaced, so ports go exactly there and nowhere else. Pure parsing lives in `zk.formats` and needs no ports.

## Consequences

- Replacing a broken tool means writing one adapter and changing one line in `zk.toml`. No stage changes.
- Stages verify adapter output against the port's contract, so a misbehaving tool fails loudly at the boundary.
- The manifest records which adapter produced each result, and the code hash covers the adapters used.
- Changing a port contract changes every adapter, so it needs a new ADR.
- The five v1 contracts are first guesses, and adapter phases may amend them through an ADR.
