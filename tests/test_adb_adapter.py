import subprocess
from pathlib import Path

import pytest

from zk.adapters import adb
from zk.ports.device_source import CONTRACT, DeviceSource

PKG = "com.zodiacknights.game"
DUMPSYS = "Packages:\n  Package [com.zodiacknights.game]\n    versionCode=17 minSdk=24\n    versionName=0.4.6\n"


class FakeAdb:
    """Answers adb commands from a table; `pull` writes a small file or raises for unreadable paths."""

    def __init__(self, devices="List of devices attached\nSER1\tdevice\n", packages=f"package:{PKG}\n",
                 paths=f"package:/data/app/~~x/{PKG}-y/base.apk\n", unreadable=(), empty=()):
        self.devices, self.packages, self.paths, self.unreadable = devices, packages, paths, set(unreadable)
        self.empty = set(empty)
        self.calls: list[list[str]] = []

    @staticmethod
    def _args(cmd):
        args = cmd[1:]
        return args[2:] if args[:1] == ["-s"] else args

    def capture(self, cmd):
        self.calls.append(cmd)
        args = self._args(cmd)
        if args == ["devices"]:
            return self.devices
        sh = " ".join(args[1:])
        return {"pm list packages": self.packages, f"dumpsys package {PKG}": DUMPSYS,
                "getprop ro.product.cpu.abi": "arm64-v8a\n", f"pm path {PKG}": self.paths}[sh]

    def run(self, cmd):
        self.calls.append(cmd)
        verb, remote, local = self._args(cmd)
        assert verb == "pull"
        if any(remote.startswith(u) for u in self.unreadable):
            raise subprocess.CalledProcessError(1, cmd)
        p = Path(local)
        if remote.endswith(".apk"):
            p.write_bytes(remote.encode())
        else:
            if p.is_dir():  # like adb: an existing local folder receives <local>/<basename>
                p = p / remote.rstrip("/").rsplit("/", 1)[1]
            p.mkdir(parents=True, exist_ok=True)
            if not any(remote.startswith(e) for e in self.empty):
                (p / "file.bin").write_bytes(b"x")


def _src(fake, serial=None):
    return adb.AdbSource("adb", capture=fake.capture, run=fake.run, serial=serial)


def test_parsers():
    assert adb.parse_devices("List of devices attached\nA\tdevice\nB\tunauthorized\n\n") == [
        ("A", "device"), ("B", "unauthorized")]
    assert adb.parse_pm_path("package:/a/base.apk\npackage:/a/split_x.apk\nnoise\n") == [
        "/a/base.apk", "/a/split_x.apk"]
    assert adb.parse_version(DUMPSYS) == ("0.4.6", "17")
    assert adb.parse_version("nothing") == (None, None)


def test_identify():
    src = _src(FakeAdb())
    assert isinstance(src, DeviceSource)
    assert src.identify(PKG) == {"package": PKG, "version": "0.4.6-17", "abi": "arm64-v8a"}


@pytest.mark.parametrize("fake, match", [
    (FakeAdb(devices="List of devices attached\n"), "no device"),
    (FakeAdb(devices="List of devices attached\nS\tunauthorized\n"), "not ready"),
    (FakeAdb(devices="List of devices attached\nA\tdevice\nB\tdevice\n"), "ANDROID_SERIAL"),
    (FakeAdb(packages="package:com.other\n"), "not installed"),
])
def test_identify_failures(fake, match):
    with pytest.raises(RuntimeError, match=match):
        _src(fake).identify(PKG)


def test_serial_picks_one_of_many(tmp_path):
    fake = FakeAdb(devices="List of devices attached\nA\tdevice\nB\tdevice\n")
    src = _src(fake, serial="B")
    assert src.identify(PKG)["version"] == "0.4.6-17"
    src.pull(PKG, tmp_path)
    rest = [c for c in fake.calls if c != ["adb", "devices"]]
    assert rest and all(c[1:3] == ["-s", "B"] for c in rest)
    with pytest.raises(RuntimeError, match="not among"):
        _src(fake, serial="C").identify(PKG)


def test_pull_every_split_and_tolerates_unreadable_obb(tmp_path):
    fake = FakeAdb(paths="package:/data/app/x/base.apk\npackage:/data/app/x/split_config.arm64_v8a.apk\n",
                   unreadable=("/sdcard/Android/obb/",))
    info = _src(fake).pull(PKG, tmp_path)
    assert info == {"pulled": {"apk": ["base.apk", "split_config.arm64_v8a.apk"], "obb": False, "data": True}}
    CONTRACT.verify(tmp_path)
    assert (tmp_path / "data" / "file.bin").exists() and not (tmp_path / "obb").exists()


def test_pull_data_failure_tolerated(tmp_path):
    fake = FakeAdb(unreadable=("/sdcard/Android/",))
    assert _src(fake).pull(PKG, tmp_path)["pulled"] == {"apk": ["base.apk"], "obb": False, "data": False}


def test_pull_without_paths_raises(tmp_path):
    with pytest.raises(RuntimeError, match="no APKs"):
        _src(FakeAdb(paths="")).pull(PKG, tmp_path)


def test_pull_empty_folder_is_not_counted(tmp_path):
    fake = FakeAdb(empty=("/sdcard/Android/obb/",))
    assert _src(fake).pull(PKG, tmp_path)["pulled"] == {"apk": ["base.apk"], "obb": False, "data": True}


def test_repull_keeps_the_same_layout(tmp_path):
    src = _src(FakeAdb())
    for _ in range(2):
        assert src.pull(PKG, tmp_path)["pulled"] == {"apk": ["base.apk"], "obb": True, "data": True}
        for kind in ("data", "obb"):
            assert sorted(p.name for p in (tmp_path / kind).iterdir()) == ["file.bin"]
        assert sorted(p.name for p in tmp_path.iterdir()) == ["apk", "data", "obb"]


def test_failed_repull_keeps_previous_copy(tmp_path):
    _src(FakeAdb()).pull(PKG, tmp_path)
    info = _src(FakeAdb(unreadable=("/sdcard/Android/data/",))).pull(PKG, tmp_path)
    assert info["pulled"]["data"] is False
    assert (tmp_path / "data" / "file.bin").exists() and not (tmp_path / ".data.partial").exists()


@pytest.mark.parametrize("failing", ["devices", "pm list packages", f"dumpsys package {PKG}"])
def test_identify_command_failure_becomes_runtime_error(failing):
    fake = FakeAdb()
    real = fake.capture

    def capture(cmd):
        if " ".join(cmd[1:]).endswith(failing):
            raise subprocess.CalledProcessError(1, cmd, stderr="error: device 'SER1' not found")
        return real(cmd)

    with pytest.raises(RuntimeError, match=r"exit 1\).*device 'SER1' not found") as exc:
        adb.AdbSource("adb", capture=capture, run=fake.run).identify(PKG)
    assert isinstance(exc.value.__cause__, subprocess.CalledProcessError)


def test_missing_adb_binary_becomes_runtime_error():
    def capture(cmd):
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    with pytest.raises(RuntimeError, match="could not run `adb devices`"):
        adb.AdbSource("adb", capture=capture, run=FakeAdb().run).identify(PKG)


def test_base_apk_pull_failure_becomes_runtime_error(tmp_path):
    fake = FakeAdb(unreadable=("/data/app/",))
    with pytest.raises(RuntimeError, match=r"pull /data/app/.*base\.apk.*exit 1") as exc:
        _src(fake).pull(PKG, tmp_path)
    assert isinstance(exc.value.__cause__, subprocess.CalledProcessError)


def test_repull_drops_splits_no_longer_installed(tmp_path):
    _src(FakeAdb(paths="package:/data/app/x/base.apk\npackage:/data/app/x/split_old.apk\n")).pull(PKG, tmp_path)
    info = _src(FakeAdb(paths="package:/data/app/x/base.apk\n")).pull(PKG, tmp_path)
    assert info["pulled"]["apk"] == ["base.apk"]
    assert sorted(p.name for p in (tmp_path / "apk").iterdir()) == ["base.apk"]
    assert not (tmp_path / ".apk.partial").exists()


def test_failed_apk_repull_keeps_previous_apks(tmp_path):
    _src(FakeAdb(paths="package:/data/app/x/base.apk\npackage:/data/app/y/split_x.apk\n")).pull(PKG, tmp_path)
    fake = FakeAdb(paths="package:/data/app/x/base.apk\npackage:/data/app/y/split_x.apk\n", unreadable=("/data/app/y/",))
    with pytest.raises(RuntimeError, match="split_x"):
        _src(fake).pull(PKG, tmp_path)
    assert sorted(p.name for p in (tmp_path / "apk").iterdir()) == ["base.apk", "split_x.apk"]
    assert not (tmp_path / ".apk.partial").exists()
