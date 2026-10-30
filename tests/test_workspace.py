import pytest

from zk.core.workspace import Workspace


def test_dir_creates_known_areas_only(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.dir("il2cpp", "1.0", "x").is_dir()
    with pytest.raises(ValueError, match="unknown workspace area"):
        ws.dir("rebuild", "1.0")


def test_record_and_manifest_roundtrip(tmp_path):
    ws = Workspace(tmp_path / "ws")
    assert ws.manifest() == {}
    ws.record("s1", {"a": 1})
    ws.record("s2", {"b": 2})
    assert ws.manifest() == {"s1": {"a": 1}, "s2": {"b": 2}}


def test_game_facts_live_in_manifest(tmp_path):
    ws = Workspace(tmp_path)
    with pytest.raises(RuntimeError, match="no game version"):
        ws.current_version()
    with pytest.raises(RuntimeError, match="metadata_version"):
        ws.fact("metadata_version")
    ws.record_facts({"version": "0.4.6-17", "metadata_version": 39})
    ws.record_facts({"unity_version": "2022.3"})
    assert ws.current_version() == "0.4.6-17"
    assert ws.fact("metadata_version") == 39
    assert ws.manifest()["game"] == {"version": "0.4.6-17", "metadata_version": 39, "unity_version": "2022.3"}


def test_fact_recorded_as_unknown_raises(tmp_path):
    ws = Workspace(tmp_path)
    ws.record_facts({"unity_version": None})
    with pytest.raises(RuntimeError, match="'unity_version' is unknown"):
        ws.fact("unity_version")
