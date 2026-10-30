import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from zk.adapters import ghidra as adapter
from zk.core import toolchain
from zk.formats import il2cpp_script
from zk.stages import ghidra as stage

OWNERS = frozenset({
    "ZodiacKnights.Game.AdminLiveOps", "ZodiacKnights.Logic.Rules", "ZodiacKnights.Game.AdminLiveOps.Inner",
    "UnityEngine.InputSystem.InputAction", "Unity.Burst.BurstCompiler", "Unity.RenderPipelines.Universal.Renderer",
    "Unity.Collections.NativeArray", "Unity.Mathematics.math", "UnityEngine.Timeline.TimelineAsset",
    "TMPro.TMP_Text", "System.String", "Mono.Runtime", "Firebase.FirebaseApp", "Google.Play.Core",
    "Kotlin.Unit", "SR", "$BurstDirectCallInitializer", "__JobReflectionRegistrationOutput__123", "GameHud",
})
NAMES = [
    "ZodiacKnights.Game.AdminLiveOps$$Start", "ZodiacKnights.Game.AdminLiveOps.<AuthenticateCo>d__54$$MoveNext",
    "ZodiacKnights.Game.AdminLiveOps.Inner$$Run", "ZodiacKnights.Logic.Rules$$Apply",
    "UnityEngine.InputSystem.InputAction$$Enable", "Unity.Burst.BurstCompiler$$Compile",
    "Unity.RenderPipelines.Universal.Renderer$$Setup", "Unity.Collections.NativeArray<int>$$Dispose",
    "Unity.Mathematics.math$$abs", "UnityEngine.Timeline.TimelineAsset$$Play", "TMPro.TMP_Text$$SetText",
    "System.String$$Concat", "Mono.Runtime$$Get", "Firebase.FirebaseApp$$Create", "Google.Play.Core$$Init",
    "Kotlin.Unit$$Get", "SR$$GetString", "$BurstDirectCallInitializer$$Initialize", "__JobReflectionRegistrationOutput__123$$Register", "GameHud$$Show",
    "Unknown.Thing$$Call",
]
METHODS = [{"Name": n, "Address": 0x100 + i} for i, n in enumerate(NAMES)]


def test_select_targets_keeps_only_game_classes():
    t = stage.select_targets(METHODS, OWNERS)
    assert list(t) == [("", "GameHud"), ("ZodiacKnights.Game", "AdminLiveOps"), ("ZodiacKnights.Logic", "Rules")]
    assert t[("ZodiacKnights.Game", "AdminLiveOps")] == [0x100, 0x101, 0x102]
    assert {stage.root_of(ns) for ns, _ in t} == {"<global>", "ZodiacKnights"}


def test_select_targets_skips_unusable_addresses_and_dedupes():
    methods = [{"Name": "ZodiacKnights.Logic.Rules$$A", "Address": 0}, {"Name": "ZodiacKnights.Logic.Rules$$B"},
               {"Name": "ZodiacKnights.Logic.Rules$$C", "Address": 5}, {"Name": "ZodiacKnights.Logic.Rules$$D", "Address": 5},
               {"Name": "ZodiacKnights.Logic.Rules$$E", "Address": True}]
    assert stage.select_targets(methods, OWNERS) == {("ZodiacKnights.Logic", "Rules"): [5]}


def test_select_targets_filter_and_limit():
    assert list(stage.select_targets(METHODS, OWNERS, pattern=r"\.Logic\.")) == [("ZodiacKnights.Logic", "Rules")]
    assert list(stage.select_targets(METHODS, OWNERS, limit=1)) == [("", "GameHud")]
    assert stage.select_targets(METHODS, OWNERS, pattern="Nope") == {}


def test_select_targets_with_type_owners_from_script():
    script = {"ScriptMethod": [{"Name": "ZodiacKnights.Game.AdminLiveOps$$Start", "Address": 1}],
              "ScriptMetadata": [{"Name": "UnityEngine.Object_TypeInfo", "Address": 2}]}
    owners = il2cpp_script.type_owners(script)
    assert stage.select_targets(script["ScriptMethod"], owners) == {("ZodiacKnights.Game", "AdminLiveOps"): [1]}


@pytest.mark.parametrize("ns,cls,expected", [
    ("ZodiacKnights.Game", "AdminLiveOps", "ZodiacKnights.Game/AdminLiveOps.c"),
    ("", "GameHud", "_global/GameHud.c"),
    ("ZodiacKnights", "<Module>", "ZodiacKnights/_Module_.c"),
])
def test_class_relpath(ns, cls, expected):
    assert stage.class_relpath(ns, cls) == expected


def test_target_lines():
    assert stage.target_lines({("A", "B"): [0x10, 0xff]}) == ["10\tA/B.c", "ff\tA/B.c"]


def test_symbol_lines_escape_and_drop_last_address():
    script = {"Addresses": [0x10, 0x20, 0x30],
              "ScriptMethod": [{"Address": 0x100, "Name": "A$$B", "Signature": "void A_B(int x);"}],
              "ScriptString": [{"Address": 0x200, "Value": "a\tb\nc\\"}],
              "ScriptMetadata": [{"Address": 0x300, "Name": "A_TypeInfo", "Signature": "A_c*"},
                                 {"Address": 0x301, "Name": "B_TypeInfo"}],
              "ScriptMetadataMethod": [{"Address": 0x400, "Name": "Method$A.B()", "MethodAddress": 0x100}]}
    assert list(adapter.symbol_lines(script)) == [
        "A\t10\t\t", "A\t20\t\t", "F\t100\tA$$B\tvoid A_B(int x)", "S\t200\tStringLiteral_0\ta\\tb\\nc\\\\",
        "M\t300\tA_TypeInfo\tA_c*", "M\t301\tB_TypeInfo\t", "N\t400\tMethod$A.B()\t"]


def test_ghidra_header_rewrites_inheritance():
    out = adapter.ghidra_header("struct B_o : Object_o {\n int x;\n};\n")
    assert out.startswith(adapter.HEADER_PRELUDE)
    assert out.endswith("struct B_o {\n Object_o super;\n int x;\n};\n")
    assert "typedef unsigned __int64 uint64_t;\n" in adapter.HEADER_PRELUDE


def test_headless_cmd_full_and_skip_analysis():
    p = Path("w")
    args = (p / "aH.bat", p / "project", p / "libil2cpp.so", p / "s.tsv", p / "h.h", p / "t.tsv", p / "f",
            p / "headless.log")
    full = adapter.headless_cmd(*args, skip_analysis=False)
    assert full[:5] == [str(p / "aH.bat"), str(p / "project"), "libil2cpp", "-import", str(p / "libil2cpp.so")]
    assert "-overwrite" in full and "-noanalysis" not in full
    pre = full.index("-preScript")
    assert full[pre + 1:pre + 5] == ["Il2CppImport.java", str(p / "s.tsv"), str(p / "h.h"), "true"]
    assert full[-4:] == ["Il2CppExport.java", str(p / "t.tsv"), str(p / "f"), "30"]
    assert full[full.index("-scriptlog") + 1] == str(p / "headless.script.log")
    skip = adapter.headless_cmd(*args, skip_analysis=True)
    assert skip[3:7] == ["-process", "libil2cpp.so", "-noanalysis", "-readOnly"]
    assert "-preScript" not in skip and "-import" not in skip
    assert skip[-4:] == full[-4:]
    assert adapter.headless_cmd(*args, skip_analysis=True, timeout=300)[-1] == "300"


def test_headless_errors_only_headless_analyzer():
    log = ("2026-10-29 08:00:00 INFO  (HeadlessAnalyzer) Import succeeded\n"
           "2026-10-29 08:00:01 ERROR (LSDACallSiteTable) noise\n"
           "2026-10-29 08:00:02 ERROR (HeadlessAnalyzer) REPORT SCRIPT ERROR: Il2CppImport.java : parse failed\n")
    assert adapter.headless_errors(log) == ["REPORT SCRIPT ERROR: Il2CppImport.java : parse failed"]
    assert adapter.headless_errors("") == []


def test_run_lines_keeps_this_run_and_continuations():
    log = ("2026-10-29 07:59:59 ERROR (HeadlessAnalyzer) old\n  old trace\n"
           "2026-10-29 08:00:00 INFO  new\n  new trace\n")
    assert adapter.run_lines(log, datetime(2026, 10, 29, 8, 0, 0)) == "2026-10-29 08:00:00 INFO  new\n  new trace\n"


def test_run_logs_includes_recent_rotations(tmp_path):
    log = tmp_path / "headless.log"
    log.write_text("", encoding="utf-8")
    old, new = tmp_path / "headless.log-1", tmp_path / "headless.log-2"
    old.write_text("", encoding="utf-8")
    new.write_text("", encoding="utf-8")
    os.utime(old, (1_000_000, 1_000_000))
    since = datetime.fromtimestamp(2_000_000)
    assert adapter.run_logs(log, since) == [new, log]
    assert adapter.run_logs(tmp_path / "none.log", since) == []


def test_ghidra_env_sets_jdk_and_heap():
    jdk = Path("tools") / "jdk"
    env = adapter.ghidra_env(jdk, "8G", {"PATH": "x", "OTHER": "1"})
    assert env["JAVA_HOME"] == str(jdk) and env["GHIDRA_HEADLESS_MAXMEM"] == "8G" and env["OTHER"] == "1"
    assert env["PATH"] == str(jdk / "bin") + os.pathsep + "x"


def test_pin_jdk_rewrites_launch_properties(tmp_path):
    props = tmp_path / "support" / "launch.properties"
    props.parent.mkdir()
    props.write_text("A=1\nJAVA_HOME_OVERRIDE=\nB=2\n", encoding="utf-8")
    adapter.pin_jdk(tmp_path, Path("C:/tools/jdk-25"))
    assert props.read_text(encoding="utf-8") == "A=1\nJAVA_HOME_OVERRIDE=C:/tools/jdk-25\nB=2\n"


START = datetime(2026, 10, 29, 8, 0, 0)


def _tools(tmp_path):
    headless = tmp_path / "tools" / "ghidra" / "support" / "analyzeHeadless.bat"
    headless.parent.mkdir(parents=True)
    (headless.parent / "launch.properties").write_text("JAVA_HOME_OVERRIDE=\n", encoding="utf-8")
    java = tmp_path / "tools" / "jdk" / "bin" / "java.exe"
    return {"ghidra": headless, "jdk25": java}


def _inputs(tmp_path):
    dump = tmp_path / "il2cpp"
    dump.mkdir()
    script = {"Addresses": [1, 2], "ScriptMethod": [{"Address": 0x10, "Name": "A$$B", "Signature": "void f();"}],
              "ScriptString": [], "ScriptMetadata": [], "ScriptMetadataMethod": []}
    (dump / "script.json").write_text(json.dumps(script), encoding="utf-8")
    (dump / "il2cpp.h").write_text("struct B : A {\n};\n", encoding="utf-8")
    targets = tmp_path / "targets.tsv"
    targets.write_text("10\tZK/A.c\n11\tZK/A.c\n20\tZK/B.c\n", encoding="utf-8")
    return dump, targets


def _headless(tmp_path, log_line="", write=("ZK/A.c", "ZK/B.c")):
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        out = tmp_path / "out"
        (out / "project" / "libil2cpp.gpr").write_text("", encoding="utf-8")
        for rel in write:
            (out / "functions" / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / "functions" / rel).write_text("// c\n", encoding="utf-8")
        (out / "headless.log").write_text(
            "2026-10-29 07:00:00 ERROR (HeadlessAnalyzer) earlier run\n"
            f"2026-10-29 08:00:01 INFO  (HeadlessAnalyzer) run\n{log_line}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    tools = _tools(tmp_path)
    g = adapter.GhidraHeadless(tmp_path / "tools", run=run, locate=lambda name, _: tools[name], maxmem="4G",
                               clock=lambda: START)
    return g, calls


def test_analyze_writes_index_and_satisfies_contract(tmp_path):
    dump, targets = _inputs(tmp_path)
    g, calls = _headless(tmp_path, write=("ZK/A.c",))
    out = tmp_path / "out"
    (out / "functions" / "ZK").mkdir(parents=True)
    (out / "functions" / "ZK" / "B.c.part").write_text("", encoding="utf-8")
    info = g.analyze(tmp_path / "libil2cpp.so", dump, targets, out, skip_analysis=False)
    assert info == {"tool": "ghidra", "version": "12.2", "jdk": "25.0.5+8", "maxmem": "4G", "decompile_timeout": 30,
                    "classes_written": 1, "classes_missing": 1, "functions_failed": 0}
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["classes"] == {"ZK/A.c": 2, "ZK/B.c": 1} and index["missing"] == ["ZK/B.c"]
    assert index["failed"] == {}
    assert index["project"] == "project/libil2cpp.gpr"
    assert not (out / "functions" / "ZK" / "B.c.part").exists()
    assert (out / "symbols.tsv").read_text(encoding="utf-8").startswith("A\t1\t\t\nF\t10\tA$$B\tvoid f()\n")
    assert "B {\n A super;" in (out / "il2cpp_ghidra.h").read_text(encoding="utf-8")
    cmd, kw = calls[0]
    assert "-import" in cmd and kw["stdin"] == subprocess.DEVNULL
    assert kw["env"]["GHIDRA_HEADLESS_MAXMEM"] == "4G"
    assert "JAVA_HOME_OVERRIDE=" + (tmp_path / "tools" / "jdk").as_posix() in (
        tmp_path / "tools" / "ghidra" / "support" / "launch.properties").read_text(encoding="utf-8")


def test_analyze_fails_on_headless_error_in_this_run(tmp_path):
    dump, targets = _inputs(tmp_path)
    g, _ = _headless(tmp_path, "2026-10-29 08:00:02 ERROR (HeadlessAnalyzer) Import failed for file\n")
    with pytest.raises(RuntimeError, match="Import failed for file"):
        g.analyze(tmp_path / "libil2cpp.so", dump, targets, tmp_path / "out", skip_analysis=False)
    assert not (tmp_path / "out" / "index.json").exists()


def test_analyze_skip_analysis_needs_saved_project(tmp_path):
    dump, targets = _inputs(tmp_path)
    g, calls = _headless(tmp_path)
    with pytest.raises(RuntimeError, match="run without --skip-analysis first"):
        g.analyze(tmp_path / "libil2cpp.so", dump, targets, tmp_path / "out", skip_analysis=True)
    assert calls == []
    (tmp_path / "out" / "project").mkdir(parents=True)
    (tmp_path / "out" / "project" / "libil2cpp.gpr").write_text("", encoding="utf-8")
    g.analyze(tmp_path / "libil2cpp.so", dump, targets, tmp_path / "out", skip_analysis=True)
    assert "-noanalysis" in calls[0][0] and not (tmp_path / "out" / "symbols.tsv").exists()


def test_create_reads_maxmem_option(tmp_path):
    class Cfg:
        tools = tmp_path
        options = {"ghidra": {"maxmem": "16G"}}
    assert adapter.create(Cfg()).maxmem == "16G"
    Cfg.options = {}
    assert adapter.create(Cfg()).maxmem == adapter.DEFAULT_MAXMEM


def test_pins_and_scripts_ship_in_package():
    assert toolchain.TOOLS["ghidra"].version == "12.2"
    assert toolchain.TOOLS["ghidra"].sha256 == "2c2cd776db3c1f6a097ba418922378ac3649cadd5e844a6f5f088ae628a7be67"
    assert toolchain.TOOLS["jdk25"].sha256
    assert {p.name for p in adapter.SCRIPTS.glob("*.java")} == {"Il2CppImport.java", "Il2CppExport.java"}
    imp = (adapter.SCRIPTS / "Il2CppImport.java").read_text(encoding="utf-8")
    assert "didParseSucceed" in imp and "Call Convention ID" in imp and "Decompiler Switch Analysis" in imp
    exp = (adapter.SCRIPTS / "Il2CppExport.java").read_text(encoding="utf-8")
    # the adapter deletes stale .part files and counts "decompilation failed: " comments
    assert '".part"' in exp and '"// decompilation failed: "' in exp
    assert "scheduleAtFixedRate" in exp and "Il2CppExport: progress " in exp


def test_create_reads_decompile_timeout_option(tmp_path):
    class Cfg:
        tools = tmp_path
        options = {"ghidra": {"decompile_timeout": "300"}}
    assert adapter.create(Cfg()).timeout == 300
    Cfg.options = {}
    assert adapter.create(Cfg()).timeout == adapter.DEFAULT_TIMEOUT
    Cfg.options = {"ghidra": {"decompile_timeout": "0"}}
    with pytest.raises(RuntimeError, match="decompile_timeout"):
        adapter.create(Cfg())


def test_failed_functions_counts_comment_lines():
    text = ("// A$$B @ 0010\nvoid f(void) {}\n\n// A$$C @ 0011\n// decompilation failed: Decompiler timeout\n\n"
            "  // decompilation failed: indented, not ours\n")
    assert adapter.failed_functions(text) == 1
    assert adapter.failed_functions("") == 0


def test_analyze_reports_failed_functions(tmp_path):
    dump, targets = _inputs(tmp_path)
    g, _ = _headless(tmp_path)
    out = tmp_path / "out"
    a = out / "functions" / "ZK" / "A.c"
    original = g.run

    def run(cmd, **kw):
        res = original(cmd, **kw)
        a.write_text("// A$$B @ 0010\n// decompilation failed: Decompiler process died: timeout\n\n"
                     "// A$$C @ 0011\nvoid c(void) {}\n", encoding="utf-8")
        return res
    g.run = run
    info = g.analyze(tmp_path / "libil2cpp.so", dump, targets, out, skip_analysis=False)
    assert info["functions_failed"] == 1 and info["classes_written"] == 2
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["failed"] == {"ZK/A.c": 1}
