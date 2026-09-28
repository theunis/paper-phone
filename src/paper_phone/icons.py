"""Lucide icons (ISC licence), vendored as SVG files under assets/icons."""

from __future__ import annotations

import re
from functools import cache
from importlib import resources

ICONS = resources.files("paper_phone") / "assets" / "icons"


@cache
def icon_paths(name: str) -> str:
    """The inner SVG elements of an icon (24x24 viewBox, stroke-based)."""
    text = (ICONS / f"{name}.svg").read_text(encoding="utf-8")
    inner = text.split(">", 2)[-1] if text.startswith("<!--") else text.split(">", 1)[-1]
    inner = inner.rsplit("</svg>", 1)[0]
    return re.sub(r"\s+", " ", inner).strip()


def icon(name: str, cls: str = "i", stroke: float = 2.0) -> str:
    """An inline <svg> that inherits `color` and scales with font-size (1em)."""
    return (
        f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{icon_paths(name)}</svg>'
    )
