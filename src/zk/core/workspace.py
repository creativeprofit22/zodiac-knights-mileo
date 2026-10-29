"""Workspace layout: the only contract between stages.

workspace/
  raw/<version>/       files pulled from the phone (APK, OBB, data)
  unpacked/<version>/  APK contents (zip extracted)
  il2cpp/<version>/    il2cpp_dump port output (dump.cs, script.json, DummyDll/)
  code/<version>/      java_decompiler port output (Java sources)
  types/<version>/     type_info port output (nodes.json)
  ghidra/<version>/    ghidra port output (index.json, functions/, project/)
  assets/<version>/    exported Unity assets
  data/<version>/      decoded game tables
  manifest.json        "game" facts + what each stage produced (stage -> info)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

STAGE_DIRS = ("raw", "unpacked", "il2cpp", "code", "csharp", "types", "ghidra", "assets", "data")
GAME = "game"  # manifest key holding facts about the game build (never hard-coded constants)


@dataclass
class Workspace:
    root: Path

    def dir(self, kind: str, version: str, *parts: str) -> Path:
        if kind not in STAGE_DIRS:
            raise ValueError(f"unknown workspace area: {kind}")
        p = self.root.joinpath(kind, version, *parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {}

    def record(self, stage: str, info: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        m = self.manifest()
        m[stage] = info
        self.manifest_path.write_text(json.dumps(m, indent=2, default=str), encoding="utf-8")

    def facts(self) -> dict:
        return dict(self.manifest().get(GAME, {}))

    def fact(self, name: str):
        facts = self.facts()
        if name not in facts:
            raise RuntimeError(f"game fact {name!r} not recorded yet: run the stage that discovers it first")
        return facts[name]

    def record_facts(self, facts: dict) -> None:
        self.record(GAME, {**self.facts(), **facts})

    def current_version(self) -> str:
        v = self.facts().get("version")
        if not v:
            raise RuntimeError("no game version recorded yet: run `zk acquire` first")
        return v
