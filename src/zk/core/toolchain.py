"""Portable third-party tools, pinned and downloaded into ./tools (gitignored).

Nothing is installed system-wide. Each tool is one entry in TOOLS; only adapters use them, stages never do.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from .pins import TOOLS, Tool

__all__ = ["TOOLS", "Tool", "adb", "dotnet_env", "fetch", "java_env", "java_jar", "path_of", "run"]



def fetch(tool: Tool, tools_dir: Path) -> Path:
    """Download and unpack a tool if missing; return its entry path."""
    home = tool.home(tools_dir)
    entry = home / tool.entry
    if entry.exists():
        return entry
    if not tool.sha256:
        raise RuntimeError(f"{tool.name} {tool.version}: no sha256 pinned in TOOLS; pin it before fetching")
    home.mkdir(parents=True, exist_ok=True)
    tmp = home / ("download.zip" if tool.kind == "zip" else tool.entry + ".part")
    print(f"[tools] downloading {tool.name} {tool.version}")
    digest = hashlib.sha256()
    with urllib.request.urlopen(tool.url) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            digest.update(chunk)
            f.write(chunk)
    if digest.hexdigest() != tool.sha256.lower():
        tmp.unlink()
        raise RuntimeError(f"{tool.name} {tool.version}: sha256 mismatch "
                           f"(expected {tool.sha256}, got {digest.hexdigest()})")
    if tool.kind == "zip":
        with zipfile.ZipFile(tmp) as z:
            z.extractall(home)
        tmp.unlink()
    else:
        tmp.replace(entry)
    if not entry.exists():
        raise RuntimeError(f"{tool.name}: expected {entry} after download")
    return entry


def path_of(name: str, tools_dir: Path) -> Path:
    return fetch(TOOLS[name], tools_dir)


def dotnet_env(tools_dir: Path) -> dict[str, str]:
    """Environment that runs .NET 10 apps on the portable runtime, ignoring any system install."""
    root = path_of("dotnet10", tools_dir).parent
    return {**os.environ, "DOTNET_ROOT": str(root), "DOTNET_MULTILEVEL_LOOKUP": "0"}


def java_env(tools_dir: Path) -> dict[str, str]:
    """Environment that runs Java tools on the pinned JDK 21, ignoring any system Java."""
    home = path_of("jdk21", tools_dir).parents[1]
    return {**os.environ, "JAVA_HOME": str(home)}


def adb() -> str:
    """Locate adb: PATH, then the Android SDK default location."""
    if found := shutil.which("adb"):
        return found
    for base in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")):
        if base:
            p = Path(base) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
            if p.exists():
                return str(p)
    raise RuntimeError("adb not found (install Android platform-tools or set ANDROID_HOME)")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("[run]", " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def java_jar(jar: Path, *args) -> list[str]:
    return ["java", "-jar", str(jar), *map(str, args)]
