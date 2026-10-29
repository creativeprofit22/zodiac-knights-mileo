"""Investigated explanations, keyed so the report can tell explained from unexplained.

MONOBEHAVIOURS: "<assembly>|<class>" -> why that class cannot be read through type_info nodes.
CROSSCHECK_RULES: class-name regex -> the counting/naming rule behind a dump vs crosscheck difference.
Each entry needs evidence in docs/stages/assets.md; add one only after investigating the real failure.
"""
from __future__ import annotations

MONOBEHAVIOURS: dict[str, str] = {}
CROSSCHECK_RULES: dict[str, str] = {}
