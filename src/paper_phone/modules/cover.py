"""Page 1: the "lock screen" — date, weather at a glance and an app grid as contents."""

from __future__ import annotations

import datetime as dt
from typing import Any

from paper_phone.build import Data
from paper_phone.modules.core import (
    DAY_ABBR,
    DAY_NAME,
    MONTH_ABBR,
    MONTH_NAME,
    REGISTRY,
    PageCtx,
    d_range,
    d_short,
    duration,
    module,
    t_hm,
)
from paper_phone.modules.weather import trip_days
from paper_phone.sources import astro, content


def toc(data: Data) -> list[dict[str, Any]]:
    entries = []
    for number, spec in enumerate(data.pages, start=1):
        if number == 1:
            continue
        for key in [spec] if isinstance(spec, str) else spec:
            m = REGISTRY.get(key)
            if m:
                entries.append({"title": m.title, "icon": m.icon, "color": m.color, "page": number})
    if data.maps:
        entries.append({"title": "Maps", "icon": "map", "color": "maps", "page": "↻"})
    if len(entries) > 8:
        entries = [e for e in entries if e["page"] != 8]
    return entries[:8]


@module("cover", title="Paper Phone", icon="sparkles", color="cover")
def cover(data: Data, page: PageCtx) -> dict[str, Any]:
    d = data.date
    ctx: dict[str, Any] = {
        "toc": toc(data),
        "prompt": content.pick(content.prompts()["offline"], "offline", data.index)[0],
        "week": d.isocalendar()[1],
    }
    fc = data.forecast
    if data.edition == "daily":
        doy = d.timetuple().tm_yday
        days_in_year = 366 if (d.year % 4 == 0 and d.year % 100) or d.year % 400 == 0 else 365
        ctx |= {
            "kicker": DAY_NAME[d.weekday()],
            "big": str(d.day),
            "sub": f"{MONTH_NAME[d.month - 1]} {d.year}",
            "line": f"Week {ctx['week']} · day {doy} of {days_in_year}",
            "progress": doy / days_in_year,
            "today": fc.day(d) if fc else None,
            "moon": astro.moon(d),
        }
    elif data.edition == "weekly":
        ctx |= {
            "kicker": "Week",
            "big": str(ctx["week"]),
            "sub": f"{d_range(data.start, data.end)} {data.end.year}",
            "line": f"{data.place_label}",
            "strip": [
                {"abbr": DAY_ABBR[day.weekday()][0:2], "day": fc.day(day) if fc else None}
                for day in data.days
            ],
        }
    elif data.edition == "monthly":
        first, last = data.start, data.end
        facts = []
        place = data.place
        if place:
            a = astro.sun_times(first, place.lat, place.lon, data.tz)
            b = astro.sun_times(last, place.lat, place.lon, data.tz)
            if a and b:
                delta = (b[1] - b[0]) - (a[1] - a[0])
                seconds = delta.total_seconds()
                facts.append(
                    f"Days get {duration(abs(seconds))} {'longer' if seconds > 0 else 'shorter'}"
                    f" · sunrise {t_hm(a[0])} → {t_hm(b[0])}"
                )
        for day, shift in astro.clock_changes(first, last, data.tz):
            facts.append(
                f"Clocks go {'forward' if shift > 0 else 'back'} {abs(shift):g} h · {d_short(day)}"
            )
        for day, name in astro.key_phases(first, last, data.tz):
            if name in ("Full moon", "New moon"):
                facts.append(f"{name} {d_short(day)}")
        hol = [i for i in data.items if i.kind == "holiday"]
        facts += [f"{h.title} · {d_short(h.date)}" for h in hol[:2]]
        training = data.cfg.training
        if training and training.goal and first <= training.goal.date <= last:
            facts.append(f"{training.goal.name} · {d_short(training.goal.date)}")
        ctx |= {
            "kicker": str(d.year),
            "big": MONTH_NAME[d.month - 1],
            "sub": f"{(last - first).days + 1} days · weeks {first.isocalendar()[1]}–"
            f"{last.isocalendar()[1]}",
            "facts": facts[:6],
            "big_word": True,
        }
    else:
        trip = data.cfg.trip
        assert trip is not None
        today = dt.date.today()
        until = (trip.start - today).days
        if until > 1:
            countdown = f"in {until} days"
        elif until == 1:
            countdown = "tomorrow"
        elif trip.start <= today <= trip.end:
            countdown = f"day {(today - trip.start).days + 1}"
        else:
            countdown = ""
        nights = (trip.end - trip.start).days
        ctx["strip"] = [
            {"abbr": DAY_ABBR[d.date.weekday()][:2], "day": d} for d in trip_days(data)
        ][:7]
        ctx |= {
            "kicker": data.country.get("name", ""),
            "big": data.place_label,
            "big_word": True,
            "sub": f"{d_range(trip.start, trip.end)} {trip.end.year} · {nights} nights",
            "countdown": countdown,
            "legs": trip.transport[:3],
            "stay": trip.stay,
            "stay_geo": data.stay,
        }
    ctx["month_abbr"] = MONTH_ABBR
    return ctx
