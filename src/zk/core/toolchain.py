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
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tool:
    name: str
    version: str
    url: str
    entry: str  # path of the runnable file, relative to tools/<name>-<version>/
    kind: str = "zip"  # "zip" (extract) or "file" (keep as-is)
    sha256: str | None = None  # of the downloaded file; required by fetch, checked before unpacking

    def home(self, tools_dir: Path) -> Path:
        return tools_dir / f"{self.name}-{self.version}"


# sha256 values are GitHub's release-asset digests; fetch refuses unpinned tools.
TOOLS: dict[str, Tool] = {t.name: t for t in (
    Tool("jadx", "1.5.6",
         "https://github.com/skylot/jadx/releases/download/v1.5.6/jadx-1.5.6.zip",
         "bin/jadx.bat",
         sha256="545ea2be9c242511bc145755cf4bda2485ade42966e096f8b4d3da2a230e8974"),
    Tool("apktool", "3.0.3",
         "https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar",
         "apktool.jar", kind="file",
         sha256="dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"),
    # Ghidra 12 needs JDK 21; portable Temurin, only ever used via JAVA_HOME for Ghidra.
    Tool("jdk21", "21.0.12.1+1",
         "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/"
         "OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip",
         "jdk-21.0.12.1+1/bin/java.exe",
         sha256="f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e"),
    Tool("ghidra", "12.1.4",
         "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/"
         "ghidra_12.1.4_PUBLIC_20260921.zip",
         "ghidra_12.1.4_PUBLIC/support/analyzeHeadless.bat",
         sha256="ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db"),
    # Il2CppDumper and Il2CppInspector need .NET 10; portable runtime, only ever used via DOTNET_ROOT.
    # Not a GitHub asset: sha256 computed from the download after it matched Microsoft's published sha512.
    Tool("dotnet10", "10.0.14",
         "https://builds.dotnet.microsoft.com/dotnet/Runtime/10.0.14/dotnet-runtime-10.0.14-win-x64.zip",
         "dotnet.exe",
         sha256="d861ab80f232adf3bdce83293bc1fa92868400330c477bf854d8558eb91c7ca6"),
    Tool("il2cppdumper", "3.2.1",
         "https://github.com/AndnixSH/Il2CppDumper/releases/download/3.2.1/Il2CppDumper-3.2.1-win-x64.zip",
         "Il2CppDumper-3.2.1-win-x64/Il2CppDumper.exe",
         sha256="ff970e9fa3da75aaa37157c7ac669a6c022500a4c3903c966ba17a7b890160ce"),
    # AGPL-3.0: downloaded and run as an external program only, never vendored or linked.
    # The Legacy CLI is the command-line tool; the new Redux CLI is a web UI that needs ASP.NET.
    Tool("il2cppinspector", "2026.2",
         "https://github.com/LukeFZ/Il2CppInspectorRedux/releases/download/2026.2/"
         "Il2CppInspectorRedux.Legacy.CLI-win-x64.zip",
         "Il2CppInspectorRedux.Legacy.CLI-win-x64/Il2CppInspector.exe",
         sha256="f30788a94e938a96a8fcace95d22e766aed4eb721e46af2421ff399d218efd14"),
)}


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
