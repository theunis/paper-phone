"""Sheet geometry: paper sizes, panel size and the boxes on the map side."""

from __future__ import annotations

from dataclasses import dataclass

from paper_phone.config import BackLayout, Paper

PAPER_MM: dict[Paper, tuple[float, float]] = {
    "a4": (297.0, 210.0),
    "letter": (279.4, 215.9),
}
MARGIN = 6.0  # most printers cannot print the outer ~4 mm
GUTTER = 2.5  # clearance either side of the middle cut on the map side


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Sheet:
    paper: Paper

    @property
    def width(self) -> float:
        return PAPER_MM[self.paper][0]

    @property
    def height(self) -> float:
        return PAPER_MM[self.paper][1]

    @property
    def panel_w(self) -> float:
        return self.width / 4

    @property
    def panel_h(self) -> float:
        return self.height / 2


@dataclass(frozen=True)
class BackBoxes:
    maps: list[Box]  # centre first, then neighbourhoods
    info: Box | None


def back_boxes(sheet: Sheet, layout: BackLayout) -> BackBoxes:
    """Map frames on the back of the sheet.

    The middle cut runs along the horizontal centre line, so "maps" keeps every
    map clear of it: one wide city-centre map on top, two neighbourhood maps
    and an info column below.
    """
    w, h = sheet.width, sheet.height
    if layout == "blank":
        return BackBoxes([], None)
    if layout == "poster":
        return BackBoxes([Box(MARGIN, MARGIN, w - 2 * MARGIN, h - 2 * MARGIN)], None)
    top_h = h / 2 - MARGIN - GUTTER
    bottom_y = h / 2 + GUTTER
    info_w = sheet.panel_w - MARGIN - 1.5
    gap = 4.0
    map_w = (w - 2 * MARGIN - info_w - 2 * gap) / 2
    return BackBoxes(
        maps=[
            Box(MARGIN, MARGIN, w - 2 * MARGIN, top_h),
            Box(MARGIN, bottom_y, map_w, top_h),
            Box(MARGIN + map_w + gap, bottom_y, map_w, top_h),
        ],
        info=Box(w - MARGIN - info_w, bottom_y, info_w, top_h),
    )
