"""Fake il2cpp_dump adapter A: writes a synthetic dump that satisfies the contract."""
PORT = "il2cpp_dump"


class FakeDump:
    tag = "a"

    def dump(self, binary, metadata, out):
        (out / "DummyDll").mkdir(parents=True, exist_ok=True)
        (out / "dump.cs").write_text(f"// {self.tag}\n", encoding="utf-8")
        (out / "script.json").write_text("{}", encoding="utf-8")
        return {"by": self.tag}


def create(cfg):
    return FakeDump()
