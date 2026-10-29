"""Fake java_decompiler adapter: writes sources/ and reports a non-zero exit like jadx often does."""
PORT = "java_decompiler"


class FakeJavaDecompiler:
    def decompile(self, apk, out):
        (out / "sources").mkdir(parents=True, exist_ok=True)
        (out / "sources" / "A.java").write_text(f"// {apk.name}\n", encoding="utf-8")
        return {"exit_code": 1, "errors": ["ERROR - finished with errors, count: 1"]}


def create(cfg):
    return FakeJavaDecompiler()
