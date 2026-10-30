"""The `zk update` plan as data: one Step per stage, in pipeline order.

The orchestrator (zk.update) reads only these fields, so stage knowledge lives here, not in update.py.
Paths into a stage record are key tuples; "*" maps over a dict, "#" counts a list or dict.
A step reruns after an upstream only when what it `uses` from that upstream changed, so every read of an
upstream output must be declared there.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Path_ = tuple[str, ...]

SO = "unpacked/{version}/*/lib/*/libil2cpp.so"
METADATA = "unpacked/{version}/*/assets/bin/Data/Managed/Metadata/global-metadata.dat"
UNPACK_RECORD: tuple[Path_, ...] = (("il2cpp",), ("metadata", "path"), ("assemblies", "game"))


@dataclass(frozen=True)
class Uses:
    """What a step reads from one upstream step; "{version}" is filled in."""
    files: tuple[str, ...] = ()  # workspace-relative globs, content-hashed (sha256)
    trees: tuple[str, ...] = ()  # bulk folders: size+mtime manifest of every file under them
    record: tuple[Path_, ...] = ()  # values read from the upstream's manifest record


@dataclass(frozen=True)
class Step:
    name: str
    uses: dict[str, Uses] = field(default_factory=dict)
    outputs: tuple[str, ...] = ()  # workspace-relative, "{version}" filled in
    argv: tuple[str, ...] = ()
    force_argv: tuple[str, ...] = ("--force",)
    source: bool = False  # always runs; counts as unchanged when its fingerprint_keys result is unchanged
    fingerprint_keys: tuple[str, ...] = ()
    report: dict[str, Path_] = field(default_factory=dict)
    checks: dict[str, Path_] = field(default_factory=dict)
    warnings: tuple[Path_, ...] = ()
    estimate: str = ""

    @property
    def after(self) -> tuple[str, ...]:
        return tuple(self.uses)


STEPS: tuple[Step, ...] = (
    Step("acquire", source=True, fingerprint_keys=("version", "base_apk"),
         outputs=("raw/{version}/apk/base.apk",),
         report={"base.apk sha256": ("base_apk", "sha256"), "pulled": ("pulled",)},
         estimate="secs (a new pull: GBs)"),
    Step("unpack", uses={"acquire": Uses(record=(("base_apk", "sha256"),))}, outputs=("unpacked/{version}",),
         report={"serialized files": ("serialized_files",), "videos": ("videos", "files", "#"),
                 "unity": ("unity_version",), "metadata": ("metadata", "version")},
         warnings=(("warnings",),), estimate="~1 min"),
    Step("code", uses={"acquire": Uses(record=(("base_apk", "sha256"),)),
                       "unpack": Uses(files=(SO, METADATA, "unpacked/{version}/*/classes*.dex"),
                                      record=UNPACK_RECORD)},
         outputs=("il2cpp/{version}/summary.json", "il2cpp/{version}/crosscheck.json", "code/{version}"),
         report={"dump types": ("dump", "assemblies", "*", "types"), "java files": ("java", "java_files")},
         checks={"dumper cross-check types match": ("crosscheck", "types_match"),
                 "dumper method-gap classes": ("crosscheck", "method_gap_classes")},
         estimate="~3 min"),
    Step("csharp", uses={"unpack": Uses(files=(SO, METADATA), record=(*UNPACK_RECORD, ("unity_version",)))},
         outputs=("csharp/{version}/report.json",),
         report={"types": ("report", "*", "types")}, estimate="~1 min"),
    Step("ghidra", uses={"unpack": Uses(files=(SO,), record=(("il2cpp",),)),
                         "code": Uses(files=("il2cpp/{version}/script.json", "il2cpp/{version}/il2cpp.h"),
                                      record=(("version",), ("abi",)))},
         outputs=("ghidra/{version}/index.json", "ghidra/{version}/project"),
         report={"classes": ("classes_targeted",), "functions": ("functions_targeted",),
                 "classes missing": ("analysis", "classes_missing")},
         estimate="~45 min; ~3 h with full decompile (HDD)"),
    Step("assets", uses={"unpack": Uses(files=(SO, METADATA), trees=("unpacked/{version}/*/assets/bin/Data",),
                                        record=(*UNPACK_RECORD, ("unity_version",))),
                         "code": Uses(files=("il2cpp/{version}/summary.json", "il2cpp/{version}/crosscheck/summary.json",
                                             "il2cpp/{version}/DummyDll/*.dll"),
                                      record=(("version",),))},
         outputs=("assets/{version}/report.json", "types/{version}/nodes.json"),
         report={"exported": ("exported",), "misses": ("misses",)},
         checks={"MonoBehaviour failed": ("monobehaviours", "failed"),
                 "MonoBehaviour failures by reason": ("monobehaviours", "by_reason"),
                 "MonoBehaviour unexplained": ("monobehaviours", "unexplained"),
                 "assets cross-check unexplained": ("crosscheck", "unexplained")},
         estimate="~1-10 min"),
    Step("video", uses={"unpack": Uses(trees=("unpacked/{version}/*/assets/Video",), record=(("videos",),))},
         outputs=("assets/{version}/video/report.json",),
         report={"clips": ("clips",), "frames": ("frames",), "mismatches": ("mismatches",)},
         estimate="~1 min"),
)
