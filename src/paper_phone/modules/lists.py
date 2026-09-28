"""Checklists and writing space: tasks, packing, habits, notes, expenses."""

from __future__ import annotations

from typing import Any

from paper_phone.build import Data
from paper_phone.modules.core import DAY_ABBR, PageCtx, d_short, module
from paper_phone.modules.weather import advice


def contacts(data: Data) -> dict[str, Any]:
    """The 'if found' strip that closes the back cover."""
    facts = data.country if data.is_trip else data.home_country
    return {
        "owner": data.cfg.owner,
        "people": data.cfg.contacts[:3],
        "emergency": facts.get("emergency", "112"),
        "country": facts.get("name"),
    }


@module("tasks", title="Tasks", icon="list-checks", color="tasks", half=True)
def tasks(data: Data, page: PageCtx) -> dict[str, Any]:
    open_tasks = list(data.tasks)
    overdue = [t for t in open_tasks if t.due and t.due < data.start]
    due = [t for t in open_tasks if t.due and data.start <= t.due <= data.end]
    top = [t for t in open_tasks if t.priority][:3]
    for t in due + overdue:
        if len(top) >= 3:
            break
        if t not in top:
            top.append(t)
    rest = [t for t in open_tasks if t not in top]
    rest.sort(key=lambda t: (t.due is None, t.due or data.end))
    capacity = 17 if page.size == "full" else 6
    if data.edition == "monthly":
        capacity -= 4
    used = 3 + len(rest)
    return {
        "meta": {"daily": "Today", "weekly": "This week", "monthly": "This month"}.get(
            data.edition, ""
        ),
        "top": top,
        "top_blank": max(0, 3 - len(top)),
        "rest": rest[: max(0, capacity - 3)],
        "blank": max(0, capacity - used),
        "goals": data.edition == "monthly",
        "start": data.start,
        "d_short": d_short,
    }


def packing_list(data: Data) -> list[dict[str, Any]]:
    trip = data.cfg.trip
    nights = (trip.end - trip.start).days if trip else 3
    fc = data.forecast
    days = fc.between(data.start, data.end) if fc else []
    tips = {text for _, text in advice(days)}
    wet = any("Umbrella" in t for t in tips)
    hot = any(d.tmax >= 24 for d in days) or (data.normals is not None and data.normals.tmax >= 24)
    cold = any(d.tmin <= 8 for d in days) or (data.normals is not None and data.normals.tmin <= 8)
    home_plugs = set(data.home_country.get("plugs", []))
    away_plugs = set(data.country.get("plugs", []))
    essentials = ["Passport / ID", "Wallet & cards", "Keys", "Tickets & bookings", "Medication"]
    if away_plugs and not (away_plugs & home_plugs):
        essentials.append(f"Plug adapter ({'/'.join(sorted(away_plugs))})")
    essentials.append("Phone + charger (for emergencies)")
    clothes = [
        f"Underwear ×{nights + 1}",
        f"Socks ×{nights + 1}",
        f"Tops ×{max(2, nights // 2 + 1)}",
        "Trousers / skirt ×2",
        "Sleepwear",
        "Walking shoes",
    ]
    if cold:
        clothes.append("Warm jumper")
    if wet:
        clothes.append("Rain jacket")
    if hot:
        clothes += ["Swimwear", "Sunhat"]
    care = ["Toothbrush & paste", "Deodorant", "Shampoo", "Glasses / lenses"]
    if hot:
        care.append("Sunscreen")
    extra = ["Book", "Earplugs", "Water bottle", "Tote bag"]
    if wet:
        extra.append("Umbrella")
    if trip:
        extra += trip.packing
    return [
        {"title": "Essentials", "items": essentials},
        {"title": "Clothes", "items": clothes},
        {"title": "Wash bag", "items": care},
        {"title": "Extras", "items": extra},
    ]


@module("packing", title="Packing", icon="luggage", color="packing")
def packing(data: Data, page: PageCtx) -> dict[str, Any]:
    trip = data.cfg.trip
    nights = (trip.end - trip.start).days if trip else 0
    return {"meta": f"{nights} nights", "groups": packing_list(data)}


@module("habits", title="Habits", icon="repeat", color="habits")
def habits(data: Data, page: PageCtx) -> dict[str, Any]:
    names = data.cfg.habits[:6] or ["", "", ""]
    ctx: dict[str, Any] = {"habits": names, "contacts": contacts(data)}
    if data.edition == "monthly":
        days = data.days
        ctx |= {
            "view": "month",
            "meta": "Tick a box each day",
            "blocks": [days[:16], days[16:]],
            "day_abbr": DAY_ABBR,
        }
    else:
        ctx |= {
            "view": "week",
            "meta": f"Week {data.date.isocalendar()[1]}",
            "days": data.days if data.edition == "weekly" else data.days[:7],
            "day_abbr": DAY_ABBR,
        }
    return ctx


@module("notes", title="Notes", icon="notebook-pen", color="notes", half=True)
def notes(data: Data, page: PageCtx) -> dict[str, Any]:
    return {"meta": "", "contacts": contacts(data) if page.number == 8 else None}


@module("expenses", title="Expenses", icon="wallet", color="expenses")
def expenses(data: Data, page: PageCtx) -> dict[str, Any]:
    trip = data.cfg.trip
    currency = (trip.currency if trip else None) or data.country.get("currency", "")
    return {
        "meta": currency,
        "rows": 13,
        "contacts": contacts(data),
        "currency": currency,
    }
