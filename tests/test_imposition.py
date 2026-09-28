"""The fold only works if the sheet layout is right, so pin it down structurally."""

from __future__ import annotations

from paper_phone import imposition
from paper_phone.layout import MARGIN, Sheet, back_boxes


def test_every_page_has_its_own_panel() -> None:
    cells = {(s.row, s.col) for s in imposition.slots()}
    assert len(cells) == 8


def test_top_row_prints_upside_down() -> None:
    for s in imposition.slots():
        assert s.rotated == (s.row == 0)


def test_paper_stays_connected_in_reading_order() -> None:
    """Cut the middle half of the centre line and the panels that still share paper
    form one ring, 1 → 2 → … → 8 → 1 (the covers meet at the spine). Folding turns
    that ring into the booklet, so reading order must walk around it."""
    at = {(s.row, s.col): s.page for s in imposition.slots()}
    cut = set(imposition.cut_columns())
    edges = set()
    for (row, col), page in at.items():
        if col < 3:
            edges.add(frozenset((page, at[(row, col + 1)])))
        if row == 0 and col not in cut:
            edges.add(frozenset((page, at[(1, col)])))
    assert edges == {frozenset((n, n % 8 + 1)) for n in range(1, 9)}


def test_spreads_read_left_to_right() -> None:
    """In a spread the left page sits to the reader's left once folded.

    Upright (bottom row) pages keep their direction; upside-down pages are viewed
    from behind after the first fold, which mirrors them back."""
    for left, right in imposition.SPREADS:
        a, b = imposition.slot(left), imposition.slot(right)
        assert a.row == b.row
        if a.rotated:
            assert a.col == b.col + 1
        else:
            assert a.col + 1 == b.col


def test_front_cover_is_bottom_right_and_back_cover_beside_it() -> None:
    assert (imposition.slot(1).row, imposition.slot(1).col) == (1, 3)
    assert (imposition.slot(8).row, imposition.slot(8).col) == (1, 2)


def test_maps_on_the_back_stay_clear_of_the_cut() -> None:
    for paper in ("a4", "letter"):
        sheet = Sheet(paper)
        boxes = back_boxes(sheet, "maps")
        mid = sheet.height / 2
        for box in [*boxes.maps, boxes.info]:
            assert box is not None
            assert box.y >= MARGIN - 1e-9 and box.x >= MARGIN - 1e-9
            assert box.x + box.w <= sheet.width - MARGIN + 1e-9
            assert box.y + box.h <= sheet.height - MARGIN + 1e-9
            assert box.y + box.h < mid or box.y > mid  # never straddles the cut
