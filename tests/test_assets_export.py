import json

from tests.fakes import fake_unity as fu
from zk.stages.assets import _export


def _idx(tmp_path):
    return _export.Index(tmp_path / _export.INDEX)


def test_media_writers(tmp_path):
    idx = _idx(tmp_path)
    cases = [(fu.texture(1, "a/b"), "textures/a_b_1.png"), (fu.sprite(2), "sprites/spr_2.png"),
             (fu.audio(3), "audio/clip_3.wav"), (fu.font(4), "fonts/font_4.ttf"),
             (fu.font(5, data=b"OTTOxx"), "fonts/font_5.otf"), (fu.text(6), "text/notes_6.txt"),
             (fu.text(7, script=b"\xff\xfe"), "text/notes_7.bytes")]
    for obj, rel in cases:
        e = _export.export_media(obj, tmp_path, idx)
        assert (e["status"], e["out"]) == ("ok", rel)
        assert (tmp_path / rel).is_file()
    multi = _export.export_media(fu.audio(8, samples={"b": b"2", "a": b"1"}), tmp_path, idx)
    assert multi["out"] == "audio/clip_8_0_a.wav" and (tmp_path / "audio/clip_8_1_b.wav").read_bytes() == b"2"


def test_media_misses_are_named(tmp_path):
    idx = _idx(tmp_path)
    assert _export.export_media(fu.texture(1, width=0), tmp_path, idx)["error"] == "empty texture (m_Width 0)"
    assert _export.export_media(fu.font(2, data=b""), tmp_path, idx)["status"] == "missed"
    broken = fu.texture(3)
    broken.payload = ValueError("ASTC decode failed")
    assert _export.export_media(broken, tmp_path, idx)["error"] == "ValueError: ASTC decode failed"


def test_name_clash_adds_source_file(tmp_path):
    idx = _idx(tmp_path)
    a = _export.export_media(fu.texture(1, "x", file="f1"), tmp_path, idx)
    b = _export.export_media(fu.texture(1, "x", file="f2"), tmp_path, idx)
    assert (a["out"], b["out"]) == ("textures/x_1.png", "textures/x_1_f2.png")


def test_monobehaviour_json_and_failure_reasons(tmp_path):
    idx = _idx(tmp_path)
    nodes = {"UI|UI.Image": [{"m_Type": "MonoBehaviour", "m_Name": "Base", "m_Level": 0}]}
    missing = {"UI|UI.Gone": "AssertionError: failed to dump nodes raw"}
    ok = _export.export_monobehaviour(fu.mono(1, ("UI", "UI.Image"), name="img"), ("UI", "UI.Image"),
                                      nodes, missing, tmp_path, idx)
    assert ok["status"] == "ok" and ok["out"] == "monobehaviours/UI/UI.Image/img_1.json"
    assert json.loads((tmp_path / ok["out"]).read_text(encoding="utf-8"))["nodes"] == 1
    cases = [(fu.mono(2, None), None, "no_script"),
             (fu.mono(3, ("UI", "UI.Gone")), ("UI", "UI.Gone"), "class_missing_in_type_info"),
             (fu.mono(4, ("UI", "UI.Image"), read_fails="read_str out of bounds"), ("UI", "UI.Image"), "read_error")]
    for obj, script, reason in cases:
        e = _export.export_monobehaviour(obj, script, nodes, missing, tmp_path, idx)
        assert (e["status"], e["reason"]) == ("failed", reason)
        assert (tmp_path / e["out"]).read_bytes() == obj.raw_bytes
    assert idx.entries == {}  # the caller records entries


def test_index_resume_and_atomic_save(tmp_path):
    idx = _idx(tmp_path)
    obj = fu.texture(1)
    idx.put(_export.key_of(obj), _export.export_media(obj, tmp_path, idx))
    idx.put("f:9", {"type": "Font", "out": None, "status": "missed", "error": "x"})
    idx.save()
    assert not (tmp_path / "index.tmp").exists()
    again = _idx(tmp_path)
    assert again.done(_export.key_of(obj)) and not again.done("f:9")
    (tmp_path / "textures/tex_1.png").unlink()
    assert not again.done(_export.key_of(obj))
