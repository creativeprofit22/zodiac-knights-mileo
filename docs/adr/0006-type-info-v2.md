# ADR 0006: `type_info` contract v2 (type-tree nodes for MonoBehaviours)

Status: accepted (amends the `type_info` part of ADR 0001)

## Context

ADR 0001 sketched `type_info` as `types(dump_dir, out)` producing `il2cpp.h` for Ghidra. ADR 0003 moved `il2cpp.h` to the `il2cpp_dump` contract, so v1 has no consumer and no adapter. The assets stage needs something else: this Unity 6 build (6000.3.2f1) ships no type trees in any serialized file, so every MonoBehaviour must be read with type-tree nodes generated from the game's assemblies. Which tool generates them (TypeTreeGeneratorAPI over DummyDll stubs, or over Cpp2IL from binary + metadata) is tool knowledge; which classes are needed is pipeline policy.

## Decision

- `type_info` becomes contract v2: `types(binary, metadata, dump_dir, unity_version, classes, out) -> dict`, `files=("nodes.json",)`.
- `unity_version` is the manifest fact from `unpack`; no adapter or stage holds a version constant.
- `classes` is a JSON file written by the stage: `[{"assembly": "UnityEngine.UI", "class": "UnityEngine.UI.Image"}, ...]`. An entry with `"reference": true` asks for a `[SerializeReference]` payload class: its nodes have no MonoBehaviour base fields.
- `nodes.json` = `{"unity_version", "classes": {"<asm>|<fullname>": [{"m_Type", "m_Name", "m_Level", "m_MetaFlag"}, ...]}, "missing": {"<asm>|<fullname>": "<error>"}, "references": {...}, "missing_references": {...}}`, keys sorted. Every requested class lands in exactly one of `classes`/`missing`, and every reference in exactly one of `references`/`missing_references`.
- Adapters use only the inputs they need: the DummyDll adapter reads `dump_dir/DummyDll/` (the `il2cpp_dump` contract); the Cpp2IL adapter reads `binary` and `metadata`.
- Output goes to `types/<version>/`.
- The assets stage reads Unity files in-process with UnityPy (MIT), the same way `zk.formats` parse bytes; it is a library, not a port. Type-tree generation stays behind this port.

## Consequences

- No adapter implemented v1, so nothing needs migrating. `il2cpp.h` stays with `il2cpp_dump`.
- UnityPy and TypeTreeGeneratorAPI are an optional `assets` extra; the core runtime stays stdlib-only and both are imported lazily.
