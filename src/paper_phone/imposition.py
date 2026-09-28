"""Where each booklet page sits on the sheet (the classic one-sheet, eight-page zine).

The sheet is landscape and divided into 4 columns x 2 rows. Viewed from the
printed side::

    +--------+--------+--------+--------+
    |   5    |   4    |   3    |   2    |   <- printed upside down
    +--------+-----------------+--------+
    |   6    |   7    |   8    |   1    |
    +--------+--------+--------+--------+
                  ^^^ cut here ^^^

Fold the sheet in half along the long middle line (print outside), cut the
middle half of that fold, open it, push the ends together so the cut opens into
a diamond, and flatten the four wings into a booklet with page 1 on top.

Why this order: after the first fold the top row sits behind the bottom row,
upside-down print becomes upright when seen from the back, and the column order
reverses. Collapsing the cross-shaped result puts the right-hand end panel (1)
in front, the back wing (2|3 and 4|5) behind it, then the left end panel and
front wing (6|7), with 8 as the back cover.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    page: int
    row: int  # 0 = top, 1 = bottom
    col: int  # 0 = left .. 3 = right
    rotated: bool  # printed upside down (180 degrees)


_LAYOUT: dict[int, tuple[int, int]] = {
    1: (1, 3),
    2: (0, 3),
    3: (0, 2),
    4: (0, 1),
    5: (0, 0),
    6: (1, 0),
    7: (1, 1),
    8: (1, 2),
}

SPREADS: tuple[tuple[int, int], ...] = ((2, 3), (4, 5), (6, 7))


def slot(page: int) -> Slot:
    row, col = _LAYOUT[page]
    return Slot(page=page, row=row, col=col, rotated=row == 0)


def slots() -> list[Slot]:
    return [slot(p) for p in range(1, 9)]


def cut_columns() -> tuple[int, int]:
    """Columns whose shared top/bottom edge is cut (the middle half)."""
    return (1, 2)
