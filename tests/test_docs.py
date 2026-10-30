"""README links every doc page, and relative links in the docs point at files that exist."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def _links(md: Path) -> set[Path]:
    text = md.read_text(encoding="utf-8")
    return {(md.parent / m).resolve() for m in LINK.findall(text) if "://" not in m}


def test_readme_links_every_doc_page():
    pages = {p.resolve() for p in (ROOT / "docs").rglob("*.md")}
    missing = sorted(str(p.relative_to(ROOT)) for p in pages - _links(ROOT / "README.md"))
    assert not missing, f"README.md does not link: {missing}"


def test_relative_doc_links_resolve():
    broken = [f"{md.relative_to(ROOT)} -> {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}"
              for md in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
              for target in sorted(_links(md)) if not target.exists()]
    assert not broken, broken
