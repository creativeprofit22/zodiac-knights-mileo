from pathlib import Path

import pytest

from zk.core.config import ROOT, Config


def test_defaults_without_file(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "src" / "zk").mkdir(parents=True)
    monkeypatch.setattr("zk.core.config.ROOT", tmp_path)
    cfg = Config.load()
    assert cfg.workspace == tmp_path / "workspace" and cfg.tools == tmp_path / "tools"
    assert cfg.adapters == {} and cfg.package is None


def test_paths_relative_to_config_folder(tmp_path):
    (tmp_path / "zk.toml").write_text(
        'workspace = "ws"\ntools = "t"\npackage = "com.x"\n[adapters]\nil2cpp_dump = "fake"\n', encoding="utf-8")
    cfg = Config.load(tmp_path / "zk.toml")
    assert cfg.workspace == (tmp_path / "ws").resolve() and cfg.tools == (tmp_path / "t").resolve()
    assert cfg.package == "com.x" and cfg.adapters == {"il2cpp_dump": "fake"}


def test_bad_adapters_table(tmp_path):
    (tmp_path / "zk.toml").write_text("[adapters]\nil2cpp_dump = 3\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="adapters"):
        Config.load(tmp_path / "zk.toml")


def test_repo_config_loads():
    cfg = Config.load()
    assert cfg.root == ROOT and (ROOT / "zk.toml").exists()


def test_explicit_missing_path_raises(tmp_path):
    with pytest.raises(RuntimeError, match="config file not found"):
        Config.load(tmp_path / "nope.toml")


def test_invalid_toml_raises_runtime_error(tmp_path):
    (tmp_path / "zk.toml").write_text("x = [\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="invalid TOML"):
        Config.load(tmp_path / "zk.toml")


def test_unknown_adapter_port_raises(tmp_path):
    (tmp_path / "zk.toml").write_text('[adapters]\nil2cppdump = "x"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"unknown port 'il2cppdump'.*il2cpp_dump"):
        Config.load(tmp_path / "zk.toml")


def test_unknown_top_level_key_raises(tmp_path):
    (tmp_path / "zk.toml").write_text('workspce = "ws"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"unknown key 'workspce'.*workspace"):
        Config.load(tmp_path / "zk.toml")


def test_installed_defaults_to_cwd(tmp_path, monkeypatch):
    site = tmp_path / "Lib"
    site.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr("zk.core.config.ROOT", site)
    monkeypatch.chdir(work)
    assert Config.load().root == Path.cwd()
