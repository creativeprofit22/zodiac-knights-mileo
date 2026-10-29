"""Fake il2cpp_dump adapter writing a synthetic script.json with game, engine and plugin methods."""
import json

from tests.fakes.fake_dump_a import FakeDump

PORT = "il2cpp_dump"
METHODS = [
    ("ZodiacKnights.Game.AdminLiveOps$$Start", 0x1000),
    ("ZodiacKnights.Game.AdminLiveOps.<AuthenticateCo>d__54$$MoveNext", 0x1010),
    ("ZodiacKnights.Logic.Rules$$Apply", 0x2000),
    ("ZodiacKnights.Logic.Rules$$Apply", 0x2000),
    ("UnityEngine.InputSystem.InputAction$$Enable", 0x3000),
    ("Unity.Burst.BurstCompiler$$Compile", 0x3010),
    ("TMPro.TMP_Text$$SetText", 0x3020),
    ("SR$$GetString", 0x3030),
    ("ZodiacKnights.Game.Unused$$Abstract", 0),
]
SCRIPT = {
    "ScriptMethod": [{"Address": a, "Name": n, "Signature": "void f();", "TypeSignature": "v"} for n, a in METHODS],
    "ScriptString": [],
    "ScriptMetadata": [{"Address": 0x9000, "Name": "ZodiacKnights.Game.Unused_TypeInfo"}],
    "ScriptMetadataMethod": [],
    "Addresses": [0x1000, 0x2000],
}


class ScriptDump(FakeDump):
    def dump(self, binary, metadata, out):
        info = super().dump(binary, metadata, out)
        (out / "script.json").write_text(json.dumps(SCRIPT), encoding="utf-8")
        return info


def create(cfg):
    return ScriptDump()
