"""device_source adapter over adb (no root): every APK split, the OBB folder, and the readable app data folder.

Runs adb through subprocess, so Git Bash path conversion never applies. Picks the device by `serial` (from ANDROID_SERIAL
via `create`), passed to adb as `-s <serial>`, when more than one is ready. Parsers adapted from SSA stages/acquire.py (6e1be49).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from zk.core import toolchain

PORT = "device_source"

Capture = Callable[[list[str]], str]  # run a command, return stdout; raises CalledProcessError on failure
Run = Callable[[list[str]], object]  # run a command for its side effects; raises CalledProcessError


def parse_devices(out: str) -> list[tuple[str, str]]:
    """`adb devices` output -> [(serial, state)]."""
    rows = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            rows.append((parts[0], parts[1]))
    return rows


def parse_pm_path(out: str) -> list[str]:
    """`pm path` / `pm list packages` output -> the values after `package:`."""
    return [ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.startswith("package:")]


def parse_version(dumpsys: str) -> tuple[str | None, str | None]:
    name = re.search(r"versionName=(\S+)", dumpsys)
    code = re.search(r"versionCode=(\d+)", dumpsys)
    return (name.group(1) if name else None, code.group(1) if code else None)


def _capture(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def _failure(cmd: list[str], e: subprocess.CalledProcessError | OSError) -> RuntimeError:
    """Turn a failed adb call into the RuntimeError the CLI reports cleanly."""
    shown = " ".join(str(c) for c in cmd)
    if isinstance(e, OSError):
        return RuntimeError(f"could not run `{shown}`: {e}")
    stderr = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
    detail = f": {stderr.strip()}" if stderr.strip() else ""
    return RuntimeError(f"`{shown}` failed (exit {e.returncode}){detail}")


class AdbSource:
    def __init__(self, adb_path: str, capture: Capture = _capture, run: Run = toolchain.run,
                 serial: str | None = None) -> None:
        self.adb = adb_path
        self.capture = capture
        self.run = run
        self.serial = serial

    def _cap(self, cmd: list[str]) -> str:
        try:
            return self.capture(cmd)
        except (subprocess.CalledProcessError, OSError) as e:
            raise _failure(cmd, e) from e

    def _cmd(self, *args: str) -> list[str]:
        return [self.adb, *(["-s", self.serial] if self.serial else []), *args]

    def _sh(self, *cmd: str) -> str:
        return self._cap(self._cmd("shell", *cmd))

    def _check_device(self) -> None:
        devices = parse_devices(self._cap([self.adb, "devices"]))
        if not devices:
            raise RuntimeError("no device seen by adb: enable USB debugging on the phone and accept the prompt")
        ready = [s for s, state in devices if state == "device"]
        if not ready:
            raise RuntimeError(f"device not ready ({devices[0][1]}): unlock the phone and accept the "
                               "USB debugging prompt")
        if len(ready) > 1 and not self.serial:
            raise RuntimeError(f"{len(ready)} devices ready ({', '.join(sorted(ready))}): "
                               "set ANDROID_SERIAL to pick one")
        if self.serial and self.serial not in ready:
            raise RuntimeError(f"ANDROID_SERIAL={self.serial} is not among the ready devices "
                               f"({', '.join(sorted(ready))})")

    def identify(self, package: str) -> dict:
        self._check_device()
        installed = set(parse_pm_path(self._sh("pm", "list", "packages")))
        if package not in installed:
            raise RuntimeError(f"package {package!r} is not installed on the device")
        vname, vcode = parse_version(self._sh("dumpsys", "package", package))
        if not vname or not vcode:
            raise RuntimeError(f"could not read versionName/versionCode of {package} from dumpsys")
        abi = self._sh("getprop", "ro.product.cpu.abi").strip()
        return {"package": package, "version": f"{vname}-{vcode}", "abi": abi or None}

    def pull(self, package: str, dest: Path) -> dict:
        remotes = parse_pm_path(self._sh("pm", "path", package))
        if not remotes:
            raise RuntimeError(f"`pm path {package}` listed no APKs")
        apk_dir = Path(dest) / "apk"
        apk_dir.mkdir(parents=True, exist_ok=True)
        names = []
        for remote in remotes:
            name = remote.rsplit("/", 1)[1]
            cmd = self._cmd("pull", remote, str(apk_dir / name))
            try:
                self.run(cmd)
            except (subprocess.CalledProcessError, OSError) as e:
                raise _failure(cmd, e) from e
            names.append(name)
        pulled: dict[str, object] = {"apk": sorted(names), "obb": False, "data": False}
        for kind, remote in (("obb", f"/sdcard/Android/obb/{package}"), ("data", f"/sdcard/Android/data/{package}")):
            pulled[kind] = self._pull_dir(remote, Path(dest), kind)
        return {"pulled": pulled}

    def _pull_dir(self, remote: str, dest: Path, kind: str) -> bool:
        """Pull `remote` so `dest/kind` holds its contents, the same on a first pull and a re-pull."""
        # adb copies into an existing local folder as <local>/<basename>, so pull into a fresh staging
        # folder and move <staging>/<basename> into place; the old copy is replaced only on success
        staging = dest / f".{kind}.partial"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            self.run(self._cmd("pull", remote, str(staging)))
        except subprocess.CalledProcessError as e:
            shutil.rmtree(staging)
            print(f"[adb] could not pull {remote} (exit {e.returncode}); continuing")
            return False
        got = staging / remote.rstrip("/").rsplit("/", 1)[1]
        target = dest / kind
        if target.exists():
            shutil.rmtree(target)
        if got.is_dir():
            got.rename(target)
        shutil.rmtree(staging)
        # adb "succeeds" on an empty folder, so only count files that arrived
        return target.is_dir() and any(p.is_file() for p in target.rglob("*"))


def create(cfg: object) -> AdbSource:
    return AdbSource(toolchain.adb(), serial=os.environ.get("ANDROID_SERIAL") or None)
