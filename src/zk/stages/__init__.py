"""Stage registry. A stage is a module exposing:

    NAME: str
    HELP: str
    def add_arguments(parser) -> None   (optional)
    def execute(ctx, args) -> dict      returns info recorded in the manifest

Stages reach tools only through ports: `ctx.adapter("<port>")`, then `PORTS["<port>"].contract.verify(out)`.
"""
from __future__ import annotations

import importlib
from types import ModuleType

# Order = natural pipeline order. Each stage phase appends its module here.
STAGE_MODULES: tuple[str, ...] = ()


def load_all(names: tuple[str, ...] | None = None) -> list[ModuleType]:
    return [importlib.import_module(f"{__name__}.{m}") for m in (STAGE_MODULES if names is None else names)]
