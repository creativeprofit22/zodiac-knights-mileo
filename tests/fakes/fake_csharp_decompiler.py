"""Fake decompiler v2 adapter: one project per name; `skip` names get no project (to test the stage check)."""
import json

from zk.formats import csharp_project

PORT = "decompiler"
SOURCE = "namespace ZK { public class A { public void Stub() { } public int Real() { return 1 + 1; } } }\n"


class FakeDecompiler:
    def __init__(self, skip):
        self.skip = skip

    def decompile(self, assemblies, names, out):
        files = {}
        for n in names:
            if not (assemblies / f"{n}.dll").is_file():
                raise RuntimeError(f"no {n}.dll")
            proj = out / "projects" / n
            proj.mkdir(parents=True, exist_ok=True)
            if n in self.skip:
                continue
            (proj / f"{n}.csproj").write_text("<Project />\n", encoding="utf-8")
            (proj / "A.cs").write_text(SOURCE, encoding="utf-8")
            files[f"{n}/A.cs"] = SOURCE
        doc = csharp_project.report(csharp_project.summarize(files), {"name": "fake"})
        (out / "report.json").write_text(json.dumps(doc), encoding="utf-8")
        return {"tool": "fake", "from": assemblies.as_posix()}


def create(cfg):
    return FakeDecompiler(set(filter(None, cfg.options.get(PORT, {}).get("skip", "").split(","))))
