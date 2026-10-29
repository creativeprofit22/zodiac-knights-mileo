"""Resolve the adapter configured for a port in zk.toml, without importing any adapter statically."""
from __future__ import annotations

import importlib
from types import ModuleType


def module_name(value: str) -> str:
    return value if "." in value else f"zk.adapters.{value}"


def load_module(port: str, cfg) -> ModuleType:
    from zk.ports import PORTS

    if port not in PORTS:
        raise RuntimeError(f"unknown port {port!r} (known: {', '.join(PORTS)})")
    value = cfg.adapters.get(port)
    if not value:
        raise RuntimeError(f"no adapter configured for port {port!r}: set [adapters] {port} = \"...\" in zk.toml")
    try:
        mod = importlib.import_module(module_name(value))
    except ModuleNotFoundError as e:
        raise RuntimeError(f"adapter {value!r} for port {port!r} not found: {e}") from e
    declared = getattr(mod, "PORT", None)
    if declared != port:
        raise RuntimeError(f"adapter {value!r} implements port {declared!r}, not {port!r}")
    if not callable(getattr(mod, "create", None)):
        raise RuntimeError(f"adapter {value!r} has no create(cfg)")
    return mod


def resolve(port: str, cfg):
    """Return (adapter instance, adapter module) for `port`, checked against the port's Protocol."""
    from zk.ports import PORTS

    mod = load_module(port, cfg)
    adapter = mod.create(cfg)
    protocol = PORTS[port].protocol
    if not isinstance(adapter, protocol):
        raise RuntimeError(f"adapter {cfg.adapters[port]!r} does not satisfy the {port} port "
                           f"({protocol.__name__})")
    return adapter, mod
