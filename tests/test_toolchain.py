import hashlib
import zipfile

import pytest

from zk.core.toolchain import Tool, fetch


def _tool(src, sha256):
    return Tool("t", "1", src.as_uri(), "t.jar", kind="file", sha256=sha256)


def test_fetch_checks_sha256(tmp_path):
    src = tmp_path / "src.jar"
    src.write_bytes(b"jar bytes")
    tools = tmp_path / "tools"
    entry = fetch(_tool(src, hashlib.sha256(b"jar bytes").hexdigest()), tools)
    assert entry == tools / "t-1" / "t.jar" and entry.read_bytes() == b"jar bytes"


def test_fetch_rejects_sha256_mismatch(tmp_path):
    src = tmp_path / "src.jar"
    src.write_bytes(b"tampered")
    tools = tmp_path / "tools"
    with pytest.raises(RuntimeError, match="sha256 mismatch"):
        fetch(_tool(src, "0" * 64), tools)
    home = tools / "t-1"
    assert not (home / "t.jar").exists() and not (home / "t.jar.part").exists()


def test_fetch_unpacks_zip(tmp_path):
    src = tmp_path / "t.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("bin/run.bat", "echo hi")
    tool = Tool("z", "2", src.as_uri(), "bin/run.bat", sha256=hashlib.sha256(src.read_bytes()).hexdigest())
    entry = fetch(tool, tmp_path / "tools")
    assert entry.read_text() == "echo hi"
    assert not (entry.parents[1] / "download.zip").exists()
    assert fetch(tool, tmp_path / "tools") == entry  # already present: no second download


def test_fetch_refuses_unpinned_tool(tmp_path):
    src = tmp_path / "src.jar"
    src.write_bytes(b"jar bytes")
    tools = tmp_path / "tools"
    with pytest.raises(RuntimeError, match="no sha256"):
        fetch(_tool(src, None), tools)
    assert not tools.exists() or not any(tools.rglob("*"))
