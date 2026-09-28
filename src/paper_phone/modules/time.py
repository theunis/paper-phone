"""Time-based pages: day timeline, week at a glance, month grid, trip itinerary."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

from paper_phone.build import Data
from paper_phone.modules.core import DAY_ABBR, MONTH_NAME, PageCtx, d_short, module, t_hm
from paper_phone.sources.agenda import Item

FIRST_HOUR, LAST_HOUR = 7, 23


def _blocks(items: list[Item]) -> tuple[list[dict[str, Any]], list[Item]]:
    """Timed items as positioned blocks (percent of the timeline), plus ones outside it."""
    span = (LAST_HOUR - FIRST_HOUR) * 60
    blocks: list[dict[str, Any]] = []
    outside: list[Item] = []
    col_end: list[int] = []
    for item in sorted((i for i in items if i.minutes), key=lambda i: i.sort_key):
        minutes = item.minutes
        if minutes is None:
            continue
        start, end = minutes
        if end <= FIRST_HOUR * 60 or start >= LAST_HOUR * 60:
            outside.append(item)
            continue
        start = max(start, FIRST_HOUR * 60)
        end = min(end, LAST_HOUR * 60)
        col = next((c for c, e in enumerate(col_end) if e <= start), len(col_end))
        if col == len(col_end):
            col_end.append(end)
        else:
            col_end[col] = end
        blocks.append(
            {
                "item": item,
                "top": (start - FIRST_HOUR * 60) / span * 100,
                "height": (end - start) / span * 100,
                "col": col,
                "short": end - start < 50,
            }
        )
    cols = max(1, len(col_end))
    for b in blocks:
        b["cols"] = cols
    return blocks, outside


@module("agenda", title="Today", icon="calendar-days", color="agenda")
def agenda(data: Data, page: PageCtx) -> dict[str, Any]:
    items = data.items_on(data.date)
    blocks, outside = _blocks(items)
    return {
        "meta": d_short(data.date),
        "all_day": [i for i in items if i.all_day],
        "blocks": blocks,
        "outside": outside,
        "hours": list(range(FIRST_HOUR, LAST_HOUR)),
    }


@module("week", title="This week", icon="calendar-range", color="agenda")
def week(data: Data, page: PageCtx) -> dict[str, Any]:
    fc = data.forecast
    days = []
    for day in data.days:
        items = data.items_on(day)
        days.append(
            {
                "date": day,
                "abbr": DAY_ABBR[day.weekday()],
                "weekend": day.weekday() >= 5,
                "evs": items[:4],
                "more": max(0, len(items) - 4),
                "holiday": next((i.title for i in items if i.kind == "holiday"), None),
                "wx": fc.day(day) if fc else None,
            }
        )
    return {"meta": f"Week {data.date.isocalendar()[1]}", "days": days}


def recurring_titles(items: list[Item], minimum: int = 3) -> set[str]:
    counts = Counter(i.title for i in items if i.kind == "event")
    return {title for title, n in counts.items() if n >= minimum}


@module("calendar", title="Calendar", icon="calendar", color="agenda")
def calendar(data: Data, page: PageCtx) -> dict[str, Any]:
    first = data.start
    recurring = recurring_titles(data.items)
    grid_start = first - dt.timedelta(days=first.weekday())
    weeks = []
    day = grid_start
    while day <= data.end:
        row = []
        for _ in range(7):
            # Recurring events are summarised under the grid; cells keep room to write.
            items = sorted(
                (
                    i
                    for i in data.items_on(day)
                    if day.month == first.month and i.title not in recurring
                ),
                key=lambda i: (i.kind != "holiday", i.sort_key),
            )
            row.append(
                {
                    "date": day,
                    "in_month": day.month == first.month,
                    "evs": items[:2],
                    "more": max(0, len(items) - 2),
                    "holiday": any(i.kind == "holiday" for i in items),
                    "weekend": day.weekday() >= 5,
                }
            )
            day += dt.timedelta(days=1)
        monday = day - dt.timedelta(days=7)
        weeks.append({"number": monday.isocalendar()[1], "days": row})
    listed = [i for i in data.items if i.title not in recurring][:8]
    return {
        "meta": f"{MONTH_NAME[first.month - 1]} {first.year}",
        "weeks": weeks,
        "abbr": [a[:2] for a in DAY_ABBR],
        "listed": listed,
        "recurring": sorted(recurring),
        "day_abbr": DAY_ABBR,
    }


@module("itinerary", title="Itinerary", icon="plane", color="agenda")
def itinerary(data: Data, page: PageCtx) -> dict[str, Any]:
    fc = data.forecast
    days = []
    for n, day in enumerate(data.days, start=1):
        items = sorted(data.items_on(day), key=lambda i: (i.start is None, i.start or dt.time()))
        days.append(
            {
                "n": n,
                "date": day,
                "label": d_short(day),
                "evs": items,
                "wx": fc.day(day) if fc else None,
            }
        )
    compact = len(days) > 5
    return {"meta": data.place_label, "days": days, "compact": compact, "t_hm": t_hm}
