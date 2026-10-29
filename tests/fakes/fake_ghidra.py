"""Fake ghidra v2 adapter: writes one .c per targets.tsv class and reports the call it got."""
import json

PORT = "ghidra"


class FakeGhidra:
    def analyze(self, binary, dump_dir, targets, out, skip_analysis):
        if not (dump_dir / "script.json").is_file() or not (dump_dir / "il2cpp.h").is_file():
            raise RuntimeError("no dump")
        (out / "project").mkdir(parents=True, exist_ok=True)
        (out / "project" / "libil2cpp.gpr").write_text("", encoding="utf-8")
        classes: dict[str, int] = {}
        for line in targets.read_text(encoding="utf-8").splitlines():
            rel = line.split("\t", 1)[1]
            classes[rel] = classes.get(rel, 0) + 1
            path = out / "functions" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// c\n", encoding="utf-8")
        (out / "index.json").write_text(json.dumps({"classes": classes, "missing": []}), encoding="utf-8")
        return {"tool": "fake", "binary": binary.name, "skip_analysis": skip_analysis}


def create(cfg):
    return FakeGhidra()
