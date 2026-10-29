# Stage: `assets`

`zk assets [--abi ABI] [--force] [--only TYPE ...] [--limit N]`, package `zk/stages/assets/`

## Purpose
Export every asset in `assets/bin/Data`. Textures and sprites become PNG, audio clips WAV, and fonts and text assets their raw files; shaders are listed. All MonoBehaviours become JSON and the scenes become hierarchy JSON. This build ships no type trees, so MonoBehaviours are read with nodes from the [type_info](../ports/type_info.md) port.

## Inputs
- `unpacked/<v>/…/assets/bin/Data` (found next to the unpack record's `global-metadata.dat`), plus `libil2cpp.so` for `--abi`.
- The `unity_version` game fact (e.g. `6000.3.2f1`) is passed to `type_info`. No version is hard-coded.
- `il2cpp/<v>/` (the `il2cpp_dump` contract) and `il2cpp/<v>/crosscheck/summary.json`. Run `zk code` without `--skip-crosscheck` first.
- Ports: `type_info`. Unity files are read in-process with UnityPy 1.25.4 (MIT, the optional `assets` extra), imported only by `_unity.py` ([ADR 0006](../adr/0006-type-info-v2.md)).

## Outputs
`assets/<v>/`:
| path | content |
|---|---|
| `textures/`, `sprites/` | `<name>_<path_id>.png` |
| `audio/` | `<name>_<path_id>.wav` (one file per FMOD sample) |
| `fonts/`, `text/` | `.ttf`/`.otf` from `m_FontData`; `.txt` (UTF-8) or `.bytes` |
| `shaders.json` | every Shader: file, path_id, name |
| `monobehaviours/<Asm>/<Class>/` | `<name>_<path_id>.json` |
| `raw/` | `<file>_<path_id>.bin` for each MonoBehaviour that could not be read |
| `scenes/<Scene>.json` | BuildSettings scene *i* = file `level<i>`: GameObjects (name, active, layer), components (type, path_id, script assembly/class), the Transform tree, plus every object in the file |
| `index.json` | `{"<file>:<path_id>": {type, name, out, status, error, ...}}` |
| `report.json` | see below |

`types/<v>/`: `classes.json` (the request) and `nodes.json` (port output).

`report.json` contains:
- `inventory`, counted live; `inventory_by_source` splits game files from the engine's built-in files (`unity default resources`, `unity_builtin_extra`).
- `exported` counts per type, and `misses` naming each object that wasn't exported, with its error.
- `monobehaviours`: `total`, `json`, `failed`, `by_reason`, and `failures`, each with its script class, assembly, reason, error, raw file and explanation.
- `assembly_resolution`: MonoScripts whose assembly doesn't define the class, re-pointed to the one dump assembly that does (e.g. `UnityEngine|UnityEngine.GUISkin` → `UnityEngine.IMGUIModule`).
- `crosscheck`, per non-game assembly used by a MonoBehaviour or one of its [SerializeReference] payloads: dump vs crosscheck type and method counts. Each differing class is tagged `used`/`rule`, with the type-count residual and the `unexplained` list.
- `scenes` and `type_info` (adapter info, including `string_array_fixes`).

Manifest record: version, unity_version, inventory, exported, misses, monobehaviours, scenes, type_info, exported_this_run.

## How MonoBehaviours are read
1. The script class comes from each MonoBehaviour's `m_Script` (MonoScript assembly, namespace, class).
2. Any `[SerializeReference]` payloads are found by scanning the object's bytes for the inline (class, namespace, assembly) names ([unity_serialized](../formats/unity_serialized.md) `managed_reference_types`). Only names the dump knows are kept. Without type trees, the file's ref-type table has no names.
3. One `type_info` call gets nodes for every script class and every referenced class (`"reference": true`).
4. Each object is read with its class nodes, and the reference nodes are attached for that read. Failure reasons are `no_script`, `class_missing_in_type_info` and `read_error`. A failure is explained only by an entry in `_known.MONOBEHAVIOURS`, which needs investigation first.

## Resume
`index.json` is saved atomically every 50 objects and on exit, including on an interrupt. A rerun skips entries that are `ok` and whose file still exists, and retries everything else. `--force` deletes only `assets/<v>/` and `types/<v>/`.

## Arguments
| flag | default | meaning |
|---|---|---|
| `--abi` | `arm64-v8a` | `libil2cpp.so` passed to `type_info` |
| `--force` | off | delete `assets/<v>/` and `types/<v>/` and export again |
| `--only` | all | any of `AudioClip Font MonoBehaviour Shader Sprite TextAsset Texture2D scene` |
| `--limit` | 0 (all) | export at most N objects this run |

## Failure modes
All of these raise `RuntimeError` (exit 2):
- There is no unpack or code record for the version, or Data doesn't look like `assets/bin/Data`.
- `il2cpp/<v>/crosscheck/summary.json` is missing: run `zk code` without `--skip-crosscheck`.
- UnityPy or TypeTreeGeneratorAPI is not installed: `pip install -e ".[assets]"`.
- Unexplained MonoBehaviour failures or unexplained crosscheck differences remain. `report.json` is still written; nothing is recorded.

## Results on 0.4.6-17 (Unity 6000.3.2f1, metadata v39)
- 1,691 files and 4,771 objects. Game files: 613 Texture2D, 15 Sprite, 539 AudioClip, 3 Font, 3 TextAsset, 42 Shader, 633 MonoBehaviour, matching the inventory. The built-in files add 37 Texture2D, 1 Font, 53 Shader and 1 MonoBehaviour.
- Everything was exported except 4 Texture2D named `Font Texture` with `m_Width 0`: dynamic font atlases that Unity fills at runtime, so they have no pixels to export.
- MonoBehaviours: 634/634 as JSON, 0 failures. Two generator defects are fixed in the adapter:
  - `string[]` fields came out typed `string`.
  - Managed-reference classes came with MonoBehaviour base fields.
  - Before these fixes, URP `UniversalRenderPipelineGlobalSettings` failed with `read_str out of bounds`.
- Crosscheck: the used non-game assemblies are Unity.InputSystem, Unity.RenderPipelines.Core.Runtime, Unity.RenderPipelines.Universal.Runtime, UnityEngine.IMGUIModule and UnityEngine.UI. Type counts are equal in all five, and no class a MonoBehaviour uses differs. The remaining method differences fall in unused classes:
  - Delegates: Il2CppInspector prints the declaration without members.
  - Nested types of generic classes: Il2CppDumper adds the outer arity, e.g. `Enumerator` vs `Enumerator`1`.
  - A few compiler-generated or overload counts.
  - The indexer counting gap (Inspector `this[...] { get => default; }`) was a parser bug, fixed in `csharp_dump` with a test.
- `Main.unity` is `level0`: a 764-byte bootstrap scene holding only RenderSettings, LightmapSettings and NavMeshSettings, so its hierarchy has no GameObjects. The game's 514 GameObjects live in prefab/content files.
- A full run takes about 2 minutes. An interrupted run resumed with exactly the 1,445 remaining objects.
- Optional external cross-check: AssetRipper 2.0.0 project export (GPL-3.0). Run it as a separate tool only; never copy its code.

## Tests
- `tests/test_stage_assets.py` runs acquire, unpack, code and assets through `cli.main` with fake adapters (`tests/fakes/fake_type_info.py`) and synthetic objects (`tests/fakes/fake_unity.py`; `_unity.load` monkeypatched). It covers:
  - the manifest unity_version flowing to type_info;
  - report counts and misses;
  - resume from the index;
  - unexplained failures and a missing crosscheck giving exit 2;
  - managed references being requested and passed to the reader.
- `tests/test_assets_export.py` covers the writers, failure reasons, name clashes and the index.
- `tests/test_assets_scene.py` covers the hierarchy, and `tests/test_assets_compare.py` covers used/unused tagging.
