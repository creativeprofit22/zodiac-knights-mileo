from tests.fakes import fake_unity as fu
from zk.stages.assets._scene import hierarchy


def test_hierarchy_nests_children_and_names_scripts():
    objs = fu.scene_objects()
    h = hierarchy(objs, lambda c: c.script())
    assert (h["game_objects"], h["components"]) == (3, 5)
    root, lone = h["roots"]
    assert (root["name"], lone["name"]) == ("Root", "Lone")
    assert root["components"][0] == {"path_id": 11, "type": "RectTransform", "transform": True}
    assert root["components"][1]["script"] == {"assembly": "UnityEngine.UI", "class": "UnityEngine.UI.CanvasScaler"}
    child = root["children"][0]
    assert (child["name"], child["active"], child["layer"]) == ("Child", False, 5)
    assert child["components"][1]["script"]["class"] == "UnityEngine.UI.Image"
    assert lone["children"] == [] and child["children"] == []


def test_external_component_keeps_file_id():
    go = fu.FakeObj("level0", 1, "GameObject", tree_doc={
        "m_Name": "X", "m_Component": [{"component": {"m_FileID": 2, "m_PathID": 7}}]})
    h = hierarchy([go], lambda c: None)
    assert h["roots"][0]["components"] == [{"path_id": 7, "type": None, "file_id": 2}]
