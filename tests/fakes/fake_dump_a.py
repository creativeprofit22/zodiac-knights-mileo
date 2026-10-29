"""Fake il2cpp_dump adapter A: writes a synthetic dump that satisfies contract v2."""
import json

PORT = "il2cpp_dump"
GAME = {"Assembly-CSharp": {"Hero": 2}, "ZodiacKnights.Game": {"ZK.Battle": 3, "ZK.Battle.Turn": 1},
        "ZodiacKnights.Logic": {"ZK.Rules": 4}}


def summary(classes_by_asm):
    return {"assemblies": {asm: {"types": len(c), "methods": sum(c.values()), "classes": dict(sorted(c.items()))}
                           for asm, c in sorted(classes_by_asm.items())}}


class FakeDump:
    tag = "a"
    game = GAME

    def dump(self, binary, metadata, out):
        (out / "DummyDll").mkdir(parents=True, exist_ok=True)
        for asm in self.game:
            (out / "DummyDll" / f"{asm}.dll").write_bytes(b"MZ")
        (out / "dump.cs").write_text(f"// {self.tag}\n", encoding="utf-8")
        (out / "script.json").write_text("{}", encoding="utf-8")
        (out / "il2cpp.h").write_text("// header\n", encoding="utf-8")
        (out / "summary.json").write_text(json.dumps(summary(self.game)), encoding="utf-8")
        return {"by": self.tag}


def create(cfg):
    return FakeDump()
