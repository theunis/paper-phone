"""Module registry and shared helpers for page modules.

A module is a function that turns the gathered `Data` into a template context.
Its template lives at templates/modules/<key>.html.j2 and is wrapped in the page
chrome (app icon, title, folio) by templates/page.html.j2.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from paper_phone.build import Data

Size = Literal["full", "half"]


@dataclass(frozen=True)
class PageCtx:
    number: int
    size: Size
    mode: str
    position: int = 0  # 0 = top half / full page, 1 = bottom half


Prepare = Callable[[Data, PageCtx], dict[str, Any]]


@dataclass(frozen=True)
class ModuleDef:
    key: str
    title: str
    icon: str
    color: str
    prepare: Prepare
    half: bool  # can share a page with another module


REGISTRY: dict[str, ModuleDef] = {}


def module(key: str, *, title: str, icon: str, color: str | None = None, half: bool = False):
    def wrap(fn: Prepare) -> Prepare:
        REGISTRY[key] = ModuleDef(key, title, icon, color or key, fn, half)
        return fn

    return wrap


# ------------------------------------------------------------- formatting

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_NAME = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_NAME = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def d_short(d: dt.date) -> str:
    """Mon 28 Sep"""
    return f"{DAY_ABBR[d.weekday()]} {d.day} {MONTH_ABBR[d.month - 1]}"


def d_long(d: dt.date) -> str:
    """Monday 28 September 2026"""
    return f"{DAY_NAME[d.weekday()]} {d.day} {MONTH_NAME[d.month - 1]} {d.year}"


def d_range(a: dt.date, b: dt.date) -> str:
    if a == b:
        return d_short(a)
    if a.month == b.month:
        return f"{a.day}–{b.day} {MONTH_ABBR[a.month - 1]}"
    return f"{a.day} {MONTH_ABBR[a.month - 1]} – {b.day} {MONTH_ABBR[b.month - 1]}"


def t_hm(t: dt.time | dt.datetime | None) -> str:
    return "" if t is None else f"{t.hour:02d}:{t.minute:02d}"


def temp(v: float | None) -> str:
    return "–" if v is None else f"{round(v):d}°"


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "–"
    minutes = round(seconds / 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def edition_meta(data: Data) -> str:
    if data.edition == "daily":
        return d_short(data.date)
    if data.edition == "weekly":
        return f"Week {data.date.isocalendar()[1]}"
    if data.edition == "monthly":
        return f"{MONTH_NAME[data.date.month - 1]} {data.date.year}"
    return data.place_label
