"""Fake type_info adapter: one node per requested class; classes named *Missing* go to `missing`."""
import json

PORT = "type_info"


class FakeTypeInfo:
    def types(self, binary, metadata, dump_dir, unity_version, classes, out):
        found, missing, refs = {}, {}, {}
        for c in json.loads(classes.read_text(encoding="utf-8")):
            key = f"{c['assembly']}|{c['class']}"
            if c.get("reference"):
                refs[key] = [{"m_Type": c["class"], "m_Name": "Base", "m_Level": 0, "m_MetaFlag": 0}]
            elif "Missing" in c["class"]:
                missing[key] = "AssertionError: failed to dump nodes raw"
            else:
                found[key] = [{"m_Type": "MonoBehaviour", "m_Name": "Base", "m_Level": 0, "m_MetaFlag": 0}]
        doc = {"unity_version": unity_version, "classes": found, "missing": missing, "references": refs,
               "missing_references": {}}
        (out / "nodes.json").write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
        return {"tool": "fake", "unity_version": unity_version, "classes": len(found), "missing": len(missing)}


def create(cfg):
    return FakeTypeInfo()
