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


def test_code_stage_tools_are_pinned():
    from zk.core.toolchain import TOOLS
    for name in ("dotnet10", "il2cppdumper", "il2cppinspector", "jadx"):
        tool = TOOLS[name]
        assert tool.sha256 and len(tool.sha256) == 64 and tool.url.startswith("https://")
        assert tool.entry.endswith((".exe", ".bat"))


def test_dotnet_env_points_at_portable_runtime(tmp_path):
    from zk.core.toolchain import TOOLS, dotnet_env
    exe = TOOLS["dotnet10"].home(tmp_path) / "dotnet.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    env = dotnet_env(tmp_path)
    assert env["DOTNET_ROOT"] == str(exe.parent) and env["DOTNET_MULTILEVEL_LOOKUP"] == "0"


def test_ghidra_pinned_to_12_2_on_jdk25():
    from zk.core.toolchain import TOOLS
    ghidra, jdk = TOOLS["ghidra"], TOOLS["jdk25"]
    assert ghidra.version == "12.2"
    assert ghidra.sha256 == "2c2cd776db3c1f6a097ba418922378ac3649cadd5e844a6f5f088ae628a7be67"
    assert ghidra.entry == "ghidra_12.2_PUBLIC/support/analyzeHeadless.bat"
    assert jdk.version.startswith("25.") and jdk.sha256 and len(jdk.sha256) == 64
    assert jdk.entry.endswith("bin/java.exe")
