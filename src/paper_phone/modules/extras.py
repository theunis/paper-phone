"""Recipe, travel practicalities, places, sudoku and offline prompts."""

from __future__ import annotations

import datetime as dt
import random
from typing import Any

import segno

from paper_phone.build import Data
from paper_phone.maps.render import POI_LABELS
from paper_phone.modules.core import PageCtx, module
from paper_phone.modules.language import numbers_for
from paper_phone.sources import content

# ---------------------------------------------------------------- recipe


@module("recipe", title="Recipe", icon="chef-hat", color="recipe")
def recipe(data: Data, page: PageCtx) -> dict[str, Any]:
    cfg = data.cfg.recipes
    extra = data.cfg.resolve(cfg.extra_file) if cfg.extra_file else None
    (r,) = content.choose_recipes(
        data.date, data.index, diet=cfg.diet, forced=cfg.pick, extra=extra, count=1
    )
    label = {"daily": "Tonight", "weekly": "This week", "monthly": "This month"}.get(
        data.edition, "Cook this"
    )
    return {"meta": label, "r": r, "two_col": len(r["ingredients"]) > 6}


# ---------------------------------------------------------------- travel


def _money_table(rate: float) -> list[tuple[str, str]]:
    rows = []
    for amount in (1, 5, 10, 20, 50, 100):
        converted = amount * rate
        text = f"{converted:,.0f}".replace(",", " ") if converted >= 100 else f"{converted:.2f}"
        rows.append((str(amount), text))
    return rows


@module("practical", title="Practical", icon="info", color="practical")
def practical(data: Data, page: PageCtx) -> dict[str, Any]:
    c = data.country
    home = data.home_country
    trip = data.cfg.trip
    base = home.get("currency", "EUR")
    quote = (trip.currency if trip else None) or c.get("currency", base)
    offset = None
    if data.home_tz is not None:
        when = dt.datetime.combine(data.start, dt.time(12), tzinfo=dt.UTC)
        here = when.astimezone(data.tz).utcoffset()
        there = when.astimezone(data.home_tz).utcoffset()
        if here is not None and there is not None:
            hours = (here - there).total_seconds() / 3600
            offset = "same as home" if hours == 0 else f"{hours:+g} h vs home"
    same_plugs = bool(set(c.get("plugs", [])) & set(home.get("plugs", [])))
    services = []
    for key, label in (("police", "Police"), ("ambulance", "Ambulance"), ("fire", "Fire")):
        if c.get(key) and c.get(key) != c.get("emergency"):
            services.append((label, c[key]))
    numbers_lang, numbers = numbers_for(data)
    return {
        "meta": c.get("name", data.place_label),
        "numbers_lang": numbers_lang,
        "numbers": numbers,
        "c": c,
        "emergency": c.get("emergency", "112"),
        "services": services,
        "base": base,
        "quote": quote,
        "rate": data.rate,
        "money": _money_table(data.rate) if data.rate and base != quote else None,
        "offset": offset,
        "same_plugs": same_plugs,
        "stay": trip.stay if trip else None,
        "stay_geo": data.stay,
    }


def _qr_svg(text: str) -> str:
    qr = segno.make(text, error="m")
    return qr.svg_inline(scale=1, border=1, dark="#000", light=None, omitsize=False)


@module("places", title="Places", icon="map-pinned", color="maps")
def places(data: Data, page: PageCtx) -> dict[str, Any]:
    results = data.extras.get("map_results", [])
    centre = results[0] if results else None
    detail = results[1] if len(results) > 1 else None
    listed = []
    for n, (place, geo) in enumerate(data.places, start=1):
        ref = next(
            (r.locate(geo.lon, geo.lat) for r in results if r.locate(geo.lon, geo.lat)), None
        )
        listed.append({"n": n, "name": place.label, "note": place.note, "ref": ref})
    nearby: list[dict[str, Any]] = []
    if detail:
        seen: set[str] = set()
        order = [
            "supermarket",
            "bakery",
            "cafe",
            "pharmacy",
            "atm",
            "station",
            "tram",
            "restaurant",
        ]
        for kind in order:
            best = sorted((p for p in detail.pois if p.kind == kind), key=lambda p: p.distance_m)
            for p in best[: 2 if kind in ("cafe", "restaurant") else 1]:
                key = f"{kind}:{p.name}"
                if key in seen:
                    continue
                seen.add(key)
                nearby.append(
                    {
                        "kind": POI_LABELS.get(kind, kind),
                        "icon": p.icon,
                        "name": p.name or POI_LABELS.get(kind, kind),
                        "walk": p.walk_min,
                        "ref": f"{detail.number} · {p.ref}",
                    }
                )
    anchor = data.stay or data.place
    qr = None
    if anchor:
        qr = _qr_svg(
            f"https://www.openstreetmap.org/?mlat={anchor.lat:.5f}&mlon={anchor.lon:.5f}"
            f"#map=17/{anchor.lat:.5f}/{anchor.lon:.5f}"
        )
    return {
        "meta": data.place_label,
        "listed": listed,
        "nearby": nearby[:9],
        "centre_title": centre.title if centre else "",
        "detail_title": detail.title if detail else "",
        "qr": qr,
    }


@module("nearby", title="Nearby", icon="map-pin", color="maps", half=True)
def nearby(data: Data, page: PageCtx) -> dict[str, Any]:
    ctx = places(data, page)
    ctx["meta"] = ctx["detail_title"]
    return ctx


# ---------------------------------------------------------------- sudoku


def _solved_grid(rng: random.Random) -> list[list[int]]:
    base = 3
    side = base * base

    def pattern(r: int, c: int) -> int:
        return (base * (r % base) + r // base + c) % side

    def shuffle(s: range) -> list[int]:
        return rng.sample(list(s), len(s))

    rows = [g * base + r for g in shuffle(range(base)) for r in shuffle(range(base))]
    cols = [g * base + c for g in shuffle(range(base)) for c in shuffle(range(base))]
    nums = shuffle(range(1, side + 1))
    return [[nums[pattern(r, c)] for c in cols] for r in rows]


def _count_solutions(grid: list[list[int]], limit: int = 2) -> int:
    for r in range(9):
        for c in range(9):
            if grid[r][c] == 0:
                total = 0
                used = set(grid[r]) | {grid[i][c] for i in range(9)}
                br, bc = 3 * (r // 3), 3 * (c // 3)
                used |= {grid[i][j] for i in range(br, br + 3) for j in range(bc, bc + 3)}
                for v in range(1, 10):
                    if v not in used:
                        grid[r][c] = v
                        total += _count_solutions(grid, limit - total)
                        grid[r][c] = 0
                        if total >= limit:
                            return total
                return total
    return 1


def sudoku_puzzle(seed: int, clues: int = 32) -> tuple[list[list[int]], list[list[int]]]:
    """A puzzle with exactly one solution, and that solution."""
    rng = random.Random(seed)
    solution = _solved_grid(rng)
    puzzle = [row[:] for row in solution]
    cells = [(r, c) for r in range(9) for c in range(9)]
    rng.shuffle(cells)
    filled = 81
    for r, c in cells:
        if filled <= clues:
            break
        keep = puzzle[r][c]
        puzzle[r][c] = 0
        if _count_solutions([row[:] for row in puzzle]) != 1:
            puzzle[r][c] = keep
        else:
            filled -= 1
    return puzzle, solution


@module("sudoku", title="Sudoku", icon="grid-3x3", color="sudoku", half=True)
def sudoku(data: Data, page: PageCtx) -> dict[str, Any]:
    puzzle, solution = sudoku_puzzle(data.index, clues=34 if data.edition == "daily" else 30)
    data.extras["sudoku_solution"] = solution
    return {"meta": "Solution on the map side", "grid": puzzle}


# ---------------------------------------------------------------- prompts


@module("prompts", title="Offline", icon="sparkles", color="prompts", half=True)
def prompts(data: Data, page: PageCtx) -> dict[str, Any]:
    p = content.prompts()
    i = data.index
    items = [
        ("Try", content.pick(p["offline"], "p-offline", i + 7)[0]),
        ("Ask someone", content.pick(p["connect"], "p-connect", i)[0]),
        ("Adventure", content.pick(p["adventure"], "p-adventure", i)[0]),
        ("Reflect", content.pick(p["reflect"], "p-reflect", i)[0]),
    ]
    if page.size == "half":
        items = items[:3]
    return {"meta": "Instead of scrolling", "entries": items}
