"""Fake il2cpp_assemblies adapter: one stub DLL per game assembly plus mscorlib."""
PORT = "il2cpp_assemblies"
NAMES = ("Assembly-CSharp", "ZodiacKnights.Game", "ZodiacKnights.Logic", "mscorlib")


class FakeAssemblies:
    def build(self, binary, metadata, unity_version, out):
        (out / "assemblies").mkdir(parents=True, exist_ok=True)
        for n in NAMES:
            (out / "assemblies" / f"{n}.dll").write_bytes(b"MZ")
        return {"tool": "fake", "unity_version": unity_version, "dlls": len(NAMES)}


def create(cfg):
    return FakeAssemblies()
