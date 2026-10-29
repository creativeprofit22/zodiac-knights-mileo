"""acquire: pull the installed game through the device_source port into raw/<version>/."""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from zk.ports import PORTS

NAME = "acquire"
HELP = "pull the game (APK splits, OBB, data) from the device source into raw/<version>/"

_LABEL = re.compile(r"^[\w.+-]+$")


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--package", help="Android package (default: `package` in zk.toml)")
    p.add_argument("--force", action="store_true", help="pull again even if raw/<version>/apk/base.apk exists")


def check_label(version: object) -> str:
    if not isinstance(version, str) or not _LABEL.match(version) or version in (".", ".."):
        raise RuntimeError(f"device source returned an unusable version label {version!r} "
                           "(letters, digits, '.', '_', '+', '-' only)")
    return version


def file_digest(path: Path) -> dict:
    with path.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    return {"sha256": sha, "bytes": path.stat().st_size}


def execute(ctx, args: argparse.Namespace) -> dict:
    package = args.package or ctx.cfg.package
    if not package:
        raise RuntimeError("no package: set `package = \"...\"` in zk.toml or pass --package")
    src = ctx.adapter("device_source")
    ident = src.identify(package)
    version = check_label(ident.get("version"))
    dest = ctx.ws.dir("raw", version)
    contract = PORTS["device_source"].contract
    pulled: dict = {}
    if args.force or contract.missing(dest):
        print(f"[acquire] pulling {package} {version} -> {dest}")
        pulled = src.pull(package, dest)
    else:
        print(f"[acquire] {dest / 'apk' / 'base.apk'} exists; skipping pull (use --force to re-pull)")
    contract.verify(dest)
    ctx.ws.record_facts({"version": version, "package": package})
    return {"package": package, "version": version, "abi": ident.get("abi"),
            "pulled": pulled.get("pulled", False),
            "base_apk": file_digest(dest / "apk" / "base.apk"), "path": str(dest)}
