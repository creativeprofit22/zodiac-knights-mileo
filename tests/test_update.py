import dataclasses
import io
import json
import sys
import re
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from tests.fakes import fake_device, fake_ghidra
from tests.fakes import fake_unity as fu
from tests.test_formats_video import rgbv_bytes
from tests.test_stage_video import _clip, _mp4
from zk import cli, stages, update
from zk.core import pins
from zk.core.context import Context
from zk.stages import code, csharp
from zk.stages.assets import _export, _unity
from zk.steps import STEPS

VERSION = "0.4.6-17"
NAMES = [s.name for s in STEPS]
ADAPTERS = {"device_source": "tests.fakes.fake_device", "il2cpp_dump": "tests.fakes.fake_dump_script",
            "il2cpp_crosscheck": "tests.fakes.fake_crosscheck", "java_decompiler": "tests.fakes.fake_java_decompiler",
            "il2cpp_assemblies": "tests.fakes.fake_il2cpp_assemblies",
            "decompiler": "tests.fakes.fake_csharp_decompiler", "ghidra": "tests.fakes.fake_ghidra",
            "type_info": "tests.fakes.fake_type_info", "video_encoder": "tests.fakes.fake_video_encoder"}


def _config(tmp_path, options=None, **override):
    lines = ['workspace = "ws"', 'tools = "tools"', 'package = "com.zodiacknights.game"', "[adapters]",
             *(f'{k} = "{v}"' for k, v in sorted({**ADAPTERS, **override}.items()))]
    for port, opts in sorted((options or {}).items()):
        lines += [f"[options.{port}]", *(f'{k} = "{v}"' for k, v in sorted(opts.items()))]
    p = tmp_path / "zk.toml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def synthetic(monkeypatch):
    """UnityPy replaced by fake objects; the fake APK carries one valid video clip."""
    monkeypatch.setattr(_unity, "load", lambda data_dir: fu.loaded([fu.texture(1), fu.sprite(3), fu.audio(4)]))
    original = fake_device.apk_files

    def apk_files(*args, **kwargs):
        files = {k: v for k, v in original(*args, **kwargs).items() if not k.startswith("assets/Video/")}
        mp4 = _mp4()
        files["assets/Video/a.mp4"], files["assets/Video/a.rgbv"] = mp4, rgbv_bytes()
        files["assets/Video/manifest.json"] = json.dumps({"version": 35, "clips": [_clip("a.mp4", mp4)]}).encode()
        return files
    monkeypatch.setattr(fake_device, "apk_files", apk_files)


def _manifest(tmp_path):
    return json.loads((tmp_path / "ws" / "manifest.json").read_text(encoding="utf-8"))


def _update(cfg, *argv):
    return cli.main(["--config", str(cfg), "update", *argv])


def _statuses(tmp_path):
    return {row["step"]: row["status"] for row in _manifest(tmp_path)["update"]["steps"]}


def _reasons(tmp_path):
    return {row["step"]: row["reason"] for row in _manifest(tmp_path)["update"]["steps"]}


def _ran(tmp_path):
    return [name for name, status in _statuses(tmp_path).items() if status == "ran"]


def _tree(root):
    return sorted((str(p.relative_to(root)), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file())


def _apk(path, unity=fake_device.UNITY):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in sorted(fake_device.apk_files(39, unity).items()):
            z.writestr(name, data)
    return path


# --- declarations ------------------------------------------------------------------------------------------

def test_steps_follow_the_stage_registry():
    assert NAMES == list(stages.STAGE_MODULES)
    for i, step in enumerate(STEPS):
        assert all(NAMES.index(u) < i for u in step.after), step.name
    assert [s.name for s in STEPS if s.source] == ["acquire"]


def test_orchestrator_has_no_stage_knowledge():
    text = Path(update.__file__).read_text(encoding="utf-8")
    for name in NAMES:
        assert not re.search(rf"[\"']{name}[\"']", text), name  # no stage name as a string literal


def test_lookup_maps_and_counts():
    rec = {"a": {"x": {"n": 1}, "y": {"n": 2}}, "l": [1, 2, 3]}
    assert update.lookup(rec, ("a", "*", "n")) == {"x": 1, "y": 2}
    assert update.lookup(rec, ("l", "#")) == 3
    assert update.lookup(rec, ("missing", "n")) is None


# --- skipping ----------------------------------------------------------------------------------------------

def test_first_run_runs_everything_and_second_run_skips_everything(tmp_path, capsys):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    assert _ran(tmp_path) == NAMES
    assert set(_reasons(tmp_path).values()) == {update.NO_STAMP}
    assert all("update_stamp" in _manifest(tmp_path)[n] for n in NAMES)
    capsys.readouterr()

    assert _update(cfg) == 0
    out = capsys.readouterr().out
    assert set(_statuses(tmp_path).values()) == {"skipped"}
    assert _reasons(tmp_path)["acquire"] == "source unchanged"
    assert "ghidra   skip  last 0s" in out
    assert "running" not in out.replace("running `zk", "", 1)  # only acquire (the source check) runs


def test_plan_shows_the_slow_ghidra_estimate(tmp_path, capsys):
    assert _update(_config(tmp_path), "--dry-run") == 0
    line = next(ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("ghidra"))
    assert "~45 min; ~3 h with full decompile (HDD)" in line and update.NO_STAMP in line


def test_manual_stage_run_drops_the_stamp(tmp_path):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    assert cli.main(["--config", str(cfg), "csharp", "--force"]) == 0
    assert "update_stamp" not in _manifest(tmp_path)["csharp"]
    assert _update(cfg) == 0
    assert _ran(tmp_path) == ["csharp"] and _reasons(tmp_path)["csharp"] == update.NO_STAMP


def test_deleted_output_reruns_that_step(tmp_path):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    (tmp_path / "ws" / "ghidra" / VERSION / "index.json").unlink()
    assert _update(cfg) == 0
    assert _ran(tmp_path) == ["ghidra"]
    assert _reasons(tmp_path)["ghidra"] == f"missing ghidra/{VERSION}/index.json"


def test_rerun_of_a_stamped_step_passes_force(tmp_path, capsys):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    (tmp_path / "ws" / "csharp" / VERSION / "report.json").unlink()
    capsys.readouterr()
    assert _update(cfg) == 0
    assert "running `zk --config " in (out := capsys.readouterr().out) and " csharp --force` (missing" in out


# --- what reruns after a change ----------------------------------------------------------------------------

def test_new_version_reruns_from_unpack(tmp_path):
    assert _update(_config(tmp_path)) == 0
    assert _update(_config(tmp_path, {"device_source": {"version": "0.4.7-1"}})) == 0
    assert _ran(tmp_path) == NAMES
    reasons = _reasons(tmp_path)
    # the fake zip's timestamps decide whether base_apk differs too, so only the prefix is fixed
    assert reasons["acquire"].startswith("option device_source.version changed; version 0.4.6-17->0.4.7-1")
    assert reasons["unpack"].startswith("version 0.4.6-17->0.4.7-1")
    assert reasons["unpack"].endswith("missing unpacked/0.4.7-1")
    assert _manifest(tmp_path)["update"]["version"] == "0.4.7-1"


def test_different_apk_through_the_folder_adapter_reruns_from_unpack(tmp_path):
    apk = _apk(tmp_path / "import" / "game.apk")
    opts = {"device_source": {"path": str(apk).replace("\\", "/"), "version": VERSION}}
    cfg = _config(tmp_path, opts, device_source="folder")
    assert _update(cfg) == 0
    assert _update(cfg) == 0 and set(_statuses(tmp_path).values()) == {"skipped"}

    _apk(apk, unity="6000.3.9f1")  # a new build under the same label needs `--force` to be pulled
    assert _update(cfg) == 0 and set(_statuses(tmp_path).values()) == {"skipped"}
    assert _update(cfg, "--force") == 0
    assert _reasons(tmp_path)["acquire"] == "base_apk changed"
    assert _manifest(tmp_path)["unpack"]["unity_version"] == "6000.3.9f1"
    assert any("6000.3.9f1" in w for w in _manifest(tmp_path)["update"]["warnings"])

    assert _update(cfg) == 0 and set(_statuses(tmp_path).values()) == {"skipped"}


def test_swapping_the_dump_adapter_reruns_code_and_its_dependents(tmp_path):
    assert _update(_config(tmp_path)) == 0
    assert _update(_config(tmp_path, il2cpp_dump="tests.fakes.fake_dump_a")) == 2  # dump a writes no script.json
    assert _statuses(tmp_path) == {"acquire": "skipped", "unpack": "skipped", "code": "ran", "csharp": "skipped",
                                   "ghidra": "failed", "assets": "not run", "video": "not run"}
    assert _reasons(tmp_path)["code"] == ("code changed; adapter il2cpp_dump: tests.fakes.fake_dump_script->"
                                          "tests.fakes.fake_dump_a")
    assert _reasons(tmp_path)["ghidra"].startswith("RuntimeError: ")
    assert "update_stamp" not in _manifest(tmp_path)["ghidra"]


def test_option_change_reruns_only_its_step(tmp_path):
    assert _update(_config(tmp_path)) == 0
    assert _update(_config(tmp_path, {"decompiler": {"skip": ""}})) == 0
    assert _ran(tmp_path) == ["csharp"]
    assert _reasons(tmp_path)["csharp"] == "option decompiler.skip changed"



def test_changed_device_abi_reruns_code_and_abi_consumers(tmp_path):
    assert _update(_config(tmp_path)) == 0
    assert _update(_config(tmp_path, {"device_source": {"abi": "x86_64"}})) == 0
    assert _ran(tmp_path) == ["acquire", "code", "csharp", "ghidra", "assets"]
    assert _reasons(tmp_path)["code"] == "acquire output abi changed"
    assert all(_manifest(tmp_path)[s]["abi"] == "x86_64" for s in ("code", "csharp", "ghidra"))

def test_unfingerprinted_option_change_skips_but_output_option_reruns(tmp_path, monkeypatch):
    monkeypatch.setattr(fake_ghidra, "UNFINGERPRINTED_OPTIONS", ("maxmem",), raising=False)
    assert _update(_config(tmp_path, {"ghidra": {"maxmem": "4G", "decompile_timeout": "30"}})) == 0
    assert _update(_config(tmp_path, {"ghidra": {"maxmem": "16G", "decompile_timeout": "30"}})) == 0
    assert set(_statuses(tmp_path).values()) == {"skipped"}
    assert _update(_config(tmp_path, {"ghidra": {"maxmem": "16G", "decompile_timeout": "300"}})) == 0
    assert _ran(tmp_path) == ["ghidra"]
    assert _reasons(tmp_path)["ghidra"] == "option ghidra.decompile_timeout changed"


def test_stamp_that_still_holds_a_now_unfingerprinted_option_is_kept(tmp_path, monkeypatch):
    cfg = _config(tmp_path, {"ghidra": {"maxmem": "4G"}})
    assert _update(cfg) == 0
    assert _manifest(tmp_path)["ghidra"]["update_stamp"]["parts"]["options"] == {"ghidra": {"maxmem": "4G"}}
    monkeypatch.setattr(fake_ghidra, "UNFINGERPRINTED_OPTIONS", ("maxmem",), raising=False)
    assert _update(cfg) == 0
    assert set(_statuses(tmp_path).values()) == {"skipped"}
    stamp = _manifest(tmp_path)["ghidra"]["update_stamp"]
    assert stamp["parts"]["options"] == {"ghidra": {}}  # rewritten on skip, no rerun
    assert _update(cfg) == 0 and set(_statuses(tmp_path).values()) == {"skipped"}


def test_pinned_tool_bump_reruns_only_its_step(tmp_path, monkeypatch):
    monkeypatch.setattr(fake_ghidra, "PINNED", ("ghidra",), raising=False)
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    old = pins.TOOLS["ghidra"]
    monkeypatch.setitem(pins.TOOLS, "ghidra", dataclasses.replace(old, version="99.0"))
    assert _update(cfg) == 0
    assert _ran(tmp_path) == ["ghidra"]
    assert _reasons(tmp_path)["ghidra"] == f"pinned tool ghidra {old.version}->99.0"


def test_force_reruns_everything(tmp_path, capsys):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    capsys.readouterr()
    assert _update(cfg, "--force") == 0
    out = capsys.readouterr().out
    assert _ran(tmp_path) == NAMES[1:]  # acquire re-pulls the same bytes, so its result is unchanged
    assert _reasons(tmp_path)["acquire"] == "source unchanged"
    assert {_reasons(tmp_path)[n] for n in NAMES[1:]} == {"--force"}
    for name in NAMES:
        assert f" {name} --force`" in out, name


# --- failure, resume, dry run ------------------------------------------------------------------------------

def _boom(ctx, args):
    raise RuntimeError("decompiler exploded")


def test_failure_stops_with_hints_and_from_resumes(tmp_path, monkeypatch, capsys):
    cfg = _config(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(csharp, "execute", _boom)
        assert _update(cfg) == 2
    err = capsys.readouterr().err
    prog = f"zk --config {cfg}"
    assert "[update] csharp failed: decompiler exploded" in err
    assert f"rerun:  {prog} csharp --force\n" in err and f"resume: {prog} update --from csharp" in err
    assert _statuses(tmp_path) == {"acquire": "ran", "unpack": "ran", "code": "ran", "csharp": "failed",
                                   "ghidra": "not run", "assets": "not run", "video": "not run"}
    assert _reasons(tmp_path)["csharp"] == "RuntimeError: decompiler exploded"
    assert _reasons(tmp_path)["ghidra"] == "earlier step failed"
    assert "update_stamp" not in _manifest(tmp_path).get("ghidra", {})

    assert _update(cfg, "--from", "csharp") == 0
    assert _statuses(tmp_path) == {"acquire": "not run", "unpack": "not run", "code": "not run", "csharp": "ran",
                                   "ghidra": "ran", "assets": "ran", "video": "ran"}
    assert _reasons(tmp_path)["code"] == "--from csharp"
    assert _update(cfg) == 0 and set(_statuses(tmp_path).values()) == {"skipped"}


def test_failed_rerun_drops_an_existing_stamp(tmp_path, monkeypatch, capsys):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    monkeypatch.setattr(csharp, "execute", _boom)
    assert _update(cfg, "--force") == 2
    assert f"rerun:  zk --config {cfg} csharp --force\n" in capsys.readouterr().err
    assert "update_stamp" not in _manifest(tmp_path)["csharp"]


def test_dry_run_writes_nothing(tmp_path, capsys):
    cfg = _config(tmp_path)
    assert _update(cfg, "--dry-run") == 0
    assert not (tmp_path / "ws").exists() or _tree(tmp_path / "ws") == []
    assert _update(cfg) == 0
    before = _tree(tmp_path / "ws")
    capsys.readouterr()

    assert _update(_config(tmp_path, il2cpp_dump="tests.fakes.fake_dump_a"), "--dry-run") == 0
    out = capsys.readouterr().out
    assert _tree(tmp_path / "ws") == before
    plan = {ln.split()[0]: ln for ln in out.splitlines()[1:] if ln.startswith("  ")}
    assert plan["acquire"].split()[1] == "check" and "checks the device source" in plan["acquire"]
    assert plan["code"].split()[1] == "run" and "adapter il2cpp_dump" in plan["code"]
    assert plan["ghidra"].split()[1] == "maybe" and plan["ghidra"].endswith("reruns if code output changes")
    assert {plan[n].split()[1] for n in ("unpack", "csharp", "video")} == {"skip"}


# --- report ------------------------------------------------------------------------------------------------

def test_report_is_printed_and_stored(tmp_path, capsys):
    cfg = _config(tmp_path, {"device_source": {"unity_version": "1234.5.6f7"}})
    ticks = iter(range(100))
    rc = update.main(Context.create(cfg), clock=lambda: float(next(ticks)),
                     now=lambda: datetime(2026, 10, 29, 12, 0, 0))
    assert rc == 0
    report = _manifest(tmp_path)["update"]
    assert update.render(report) in capsys.readouterr().out
    assert report["version"] == VERSION and report["started"] == "2026-10-29T12:00:00"
    assert report["totals"] == {"ran": 7, "skipped": 0, "failed": 0, "not run": 0}
    assert [r["seconds"] for r in report["steps"]] == [1.0] * 7
    assert report["seconds"] == 15.0
    rows = {r["step"]: r for r in report["steps"]}
    assert rows["csharp"]["counts"] == {"types": {"Assembly-CSharp": 1, "ZodiacKnights.Game": 1,
                                                  "ZodiacKnights.Logic": 1}}
    assert rows["code"]["counts"]["dump types"] == {"Assembly-CSharp": 1, "ZodiacKnights.Game": 2,
                                                    "ZodiacKnights.Logic": 1}
    assert rows["ghidra"]["counts"]["functions"] == 3 and rows["video"]["counts"]["clips"] == 1
    assert report["checks"]["dumper cross-check types match"] is True
    assert report["checks"]["MonoBehaviour failed"] == 0
    assert any(w.startswith("unpack: ") and "1234.5.6f7" in w for w in report["warnings"])
    assert _manifest(tmp_path)["ghidra"]["update_stamp"]["at"] == "2026-10-29T12:00:00"
    assert _manifest(tmp_path)["ghidra"]["update_stamp"]["seconds"] == 1.0


def test_update_is_a_reserved_stage_name():
    assert update.REPORT_KEY in cli.RESERVED_NAMES


# --- output cascade ----------------------------------------------------------------------------------------

def test_every_step_uses_only_earlier_steps():
    for i, step in enumerate(STEPS):
        assert step.after == tuple(step.uses)
        assert all(u in NAMES[:i] for u in step.uses), step.name


def _code_changed(monkeypatch):
    original = update.fingerprint_parts

    def parts(module, ports, cfg):
        out = original(module, ports, cfg)
        return {**out, "code_hash": "changed"} if module is code else out
    monkeypatch.setattr(update, "fingerprint_parts", parts)


def test_code_change_with_identical_outputs_skips_dependents(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    _code_changed(monkeypatch)
    assert _update(cfg) == 0
    assert _ran(tmp_path) == ["code"] and _reasons(tmp_path)["code"] == "code changed"
    assert {_statuses(tmp_path)[n] for n in ("csharp", "ghidra", "assets", "video")} == {"skipped"}


def test_changed_consumed_output_reruns_only_its_consumers(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    _code_changed(monkeypatch)
    original = code.execute

    def execute(ctx, args):
        out = original(ctx, args)
        with (ctx.ws.root / "il2cpp" / VERSION / "il2cpp.h").open("a", encoding="utf-8") as f:
            f.write("// changed" + chr(10))
        return out
    monkeypatch.setattr(code, "execute", execute)
    assert _update(cfg) == 0
    assert _ran(tmp_path) == ["code", "ghidra"]
    assert _reasons(tmp_path)["ghidra"] == f"code output il2cpp/{VERSION}/il2cpp.h changed"


def _legacy(tmp_path):
    path = tmp_path / "ws" / "manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    for step in STEPS:
        stamp = m[step.name]["update_stamp"]
        stamp.pop("file_cache", None)
        # old-format code stamps didn't record acquire
        inputs = {"argv": stamp["inputs"]["argv"], "upstream": {u: m[u]["update_stamp"]["fingerprint"]
                                                                for u in step.after
                                                                if (step.name, u) != ("code", "acquire")}}
        if not step.source:
            inputs["version"] = stamp["inputs"]["version"]
        stamp["inputs"] = inputs
    path.write_text(json.dumps(m), encoding="utf-8")


def test_legacy_stamps_are_adopted_without_a_rerun(tmp_path, capsys):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    _legacy(tmp_path)
    capsys.readouterr()
    assert _update(cfg, "--dry-run") == 0
    plan = {ln.split()[0]: ln.split()[1] for ln in capsys.readouterr().out.splitlines()[1:]}
    assert plan == {"acquire": "check", **{n: "skip" for n in NAMES[1:]}}
    assert _update(cfg) == 0
    assert set(_statuses(tmp_path).values()) == {"skipped"}
    stamps = {n: _manifest(tmp_path)[n]["update_stamp"] for n in NAMES[1:]}
    assert all("consumed" in s["inputs"] and "upstream" not in s["inputs"] for s in stamps.values())
    assert f"il2cpp/{VERSION}/script.json" in stamps["ghidra"]["file_cache"]


def test_dry_run_shows_maybe_for_consumers_of_a_pending_step(tmp_path, monkeypatch, capsys):
    cfg = _config(tmp_path)
    assert _update(cfg) == 0
    _code_changed(monkeypatch)
    capsys.readouterr()
    assert _update(cfg, "--dry-run") == 0
    plan = {ln.split()[0]: ln for ln in capsys.readouterr().out.splitlines()[1:]}
    assert plan["code"].split()[1] == "run"
    for name in ("ghidra", "assets"):
        assert plan[name].split()[1] == "maybe" and plan[name].endswith("reruns if code output changes")
    assert {plan[n].split()[1] for n in ("unpack", "csharp", "video")} == {"skip"}


class _Counting(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1
        super().flush()


def test_update_lines_are_flushed(tmp_path, monkeypatch):
    out = _Counting()
    monkeypatch.setattr(sys, "stdout", out)
    assert _update(_config(tmp_path), "--dry-run") == 0
    lines = [ln for ln in out.getvalue().splitlines() if ln]
    assert lines and out.flushes >= len(lines)


def test_changed_split_apk_reruns_unpack(tmp_path):
    cfg = _config(tmp_path, {"device_source": {"split_abi": "arm64-v8a"}})
    assert _update(cfg) == 0
    split = tmp_path / "ws" / "raw" / VERSION / "apk" / fake_device.split_name("arm64-v8a")
    assert split.is_file()
    fake_device.write_apk(split, {"lib/arm64-v8a/libil2cpp.so": b"\x7fELF changed"})
    assert _update(cfg) == 0
    assert _statuses(tmp_path)["acquire"] == "skipped"  # base.apk is unchanged
    assert "unpack" in _ran(tmp_path) and "code" in _ran(tmp_path)
    assert _reasons(tmp_path)["unpack"] == f"acquire output raw/{VERSION}/apk/{split.name} changed"
    assert _reasons(tmp_path)["code"].startswith(f"acquire output raw/{VERSION}/apk/{split.name} changed")
    so = tmp_path / "ws" / "unpacked" / VERSION / split.stem / "lib" / "arm64-v8a" / "libil2cpp.so"
    assert so.read_bytes() == b"\x7fELF changed"


# --- when an unstamped step is forced ----------------------------------------------------------------------

def test_manual_unpack_then_new_apk_forces_unpack(tmp_path, capsys):
    apk = _apk(tmp_path / "import" / "game.apk")
    opts = {"device_source": {"path": apk.as_posix(), "version": VERSION}}
    cfg = _config(tmp_path, opts, device_source="folder")
    assert _update(cfg) == 0
    assert cli.main(["--config", str(cfg), "unpack"]) == 0  # manual run: no stamp
    _apk(apk, unity="6000.3.9f1")
    assert cli.main(["--config", str(cfg), "acquire", "--force"]) == 0  # base.apk sha256 changes
    capsys.readouterr()
    assert _update(cfg) == 0
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("  unpack "))
    assert line.split()[1] == "run" and update.FORCED in line
    assert f" unpack --force` ({update.NO_STAMP}; {update.FORCED})" in out
    assert _manifest(tmp_path)["unpack"]["unity_version"] == "6000.3.9f1"  # not the stale unpacked folder


def _count_exports(monkeypatch, fail_at=0):
    original, calls = _export.export_media, []

    def export_media(obj, root, idx):
        calls.append(_export.key_of(obj))
        if len(calls) == fail_at:
            raise RuntimeError("disk full")
        return original(obj, root, idx)
    monkeypatch.setattr(_export, "export_media", export_media)
    return calls


def test_failed_assets_resumes_without_force(tmp_path, monkeypatch, capsys):
    cfg = _config(tmp_path)
    with monkeypatch.context() as m:
        first = _count_exports(m, fail_at=2)
        assert _update(cfg) == 2
    assert _statuses(tmp_path)["assets"] == "failed" and len(first) == 2
    capsys.readouterr()

    calls = _count_exports(monkeypatch)
    assert _update(cfg, "--from", "assets") == 0
    out = capsys.readouterr().out
    plan = next(ln for ln in out.splitlines() if ln.startswith("  assets "))
    assert update.RESUMES in plan and update.FORCED not in plan
    assert f" assets` ({update.NO_STAMP}; {update.RESUMES})" in out
    assert first[0] not in calls and first[1] in calls  # the exported object is kept, the rest resumes
    assert _statuses(tmp_path)["assets"] == "ran"
    assert _update(cfg) == 0 and set(_statuses(tmp_path).values()) == {"skipped"}


def test_failed_assets_with_changed_code_is_forced(tmp_path, monkeypatch, capsys):
    cfg = _config(tmp_path)
    with monkeypatch.context() as m:
        _count_exports(m, fail_at=2)
        assert _update(cfg) == 2
    original = update.fingerprint_parts

    def parts(module, ports, cfg):
        out = original(module, ports, cfg)
        return {**out, "code_hash": "changed"} if module.NAME == "assets" else out
    monkeypatch.setattr(update, "fingerprint_parts", parts)
    capsys.readouterr()
    assert _update(cfg, "--from", "assets") == 0
    assert f" assets --force` ({update.NO_STAMP}; {update.FORCED})" in capsys.readouterr().out
