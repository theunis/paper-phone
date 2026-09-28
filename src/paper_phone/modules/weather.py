"""Weather page: hourly chart for a day, range bars for longer spans, climate normals."""

from __future__ import annotations

from typing import Any

from paper_phone.build import Data
from paper_phone.icons import icon_paths
from paper_phone.modules.core import DAY_ABBR, PageCtx, d_short, module
from paper_phone.sources import astro
from paper_phone.sources.weather import Day, Hour


def trip_days(data: Data) -> list[Day]:
    """Forecast days for the span, filled in with climate normals beyond the horizon."""
    fc, normals = data.forecast, data.normals
    out = []
    for date in data.days:
        day = fc.day(date) if fc else None
        if day is None and normals is not None:
            sun = (
                astro.sun_times(date, data.place.lat, data.place.lon, data.tz)
                if data.place
                else None
            )
            wet = normals.wet_days_pct
            day = Day(
                date=date,
                code=2 if wet < 30 else 3 if wet < 50 else 61,
                tmax=normals.tmax,
                tmin=normals.tmin,
                precip=normals.precip_mm_per_day,
                precip_prob=round(wet),
                sunrise=sun[0] if sun else None,
                sunset=sun[1] if sun else None,
                daylight_s=(sun[1] - sun[0]).total_seconds() if sun else None,
                uv=None,
                wind_max=None,
                wind_dir=None,
                typical=True,
            )
        if day is not None:
            out.append(day)
    return out


def advice(days: list[Day]) -> list[tuple[str, str]]:
    """Plain-language hints, (icon, text)."""
    if not days:
        return []
    out = []
    wet = [
        d
        for d in days
        if (d.typical and (d.precip_prob or 0) >= 45)
        or (not d.typical and (d.precip >= 1 or (d.precip_prob or 0) >= 55))
    ]
    if wet:
        out.append(("umbrella", "Umbrella" if len(days) == 1 else f"Umbrella: {len(wet)} wet days"))
    if max(d.tmax for d in days) >= 25:
        out.append(("sun", "Sunscreen & water"))
    elif max((d.uv or 0) for d in days) >= 6:
        out.append(("sun", "High UV: sunscreen"))
    if min(d.tmin for d in days) <= 4:
        out.append(("snowflake", "Hat & gloves"))
    elif min(d.tmin for d in days) <= 10:
        out.append(("shirt", "Bring a warm layer"))
    if max(d.beaufort for d in days) >= 6:
        out.append(("wind", "Windy"))
    if not out:
        out.append(("sparkles", "Easy weather, go outside"))
    return out[:3]


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def hourly_svg(hours: list[Hour], width: float) -> str:
    hours = [h for h in hours if 6 <= h.time.hour <= 23]
    if len(hours) < 4:
        return ""
    temp_top, temp_h, gap, rain_h, axis_h = 7.4, 17.0, 2.6, 6.0, 2.6
    height = temp_top + temp_h + gap + rain_h + axis_h
    pad = 2.2
    first, last = hours[0].time.hour, hours[-1].time.hour

    def x(hour: int) -> float:
        return pad + (hour - first) / max(1, last - first) * (width - 2 * pad)

    temps = [h.temp for h in hours]
    lo, hi = min(temps) - 0.8, max(temps) + 0.8
    if hi - lo < 5:
        mid = (hi + lo) / 2
        lo, hi = mid - 2.5, mid + 2.5

    def y(t: float) -> float:
        return temp_top + (hi - t) / (hi - lo) * temp_h

    parts = []
    # faint guides at 0 deg if in range, and at the rain baseline
    rain_base = temp_top + temp_h + gap + rain_h
    parts.append(
        f'<line x1="0" x2="{_f(width)}" y1="{_f(rain_base)}" y2="{_f(rain_base)}" class="wx-axis"/>'
    )
    if lo < 0 < hi:
        parts.append(
            f'<line x1="0" x2="{_f(width)}" y1="{_f(y(0))}" y2="{_f(y(0))}" class="wx-zero"/>'
        )
    # rain bars (mm per hour)
    cap = max(2.0, max(h.precip for h in hours))
    bar_w = max(0.6, (width - 2 * pad) / max(1, last - first) * 0.62)
    for h in hours:
        if h.precip <= 0.05:
            continue
        bh = max(0.35, h.precip / cap * rain_h)
        parts.append(
            f'<rect x="{_f(x(h.time.hour) - bar_w / 2)}" y="{_f(rain_base - bh)}" '
            f'width="{_f(bar_w)}" height="{_f(bh)}" rx=".25" class="wx-bar"/>'
        )
    # temperature line
    pts = " ".join(f"{_f(x(h.time.hour))},{_f(y(h.temp))}" for h in hours)
    parts.append(f'<polyline points="{pts}" class="wx-line"/>')
    tmax_hour = max(hours, key=lambda h: h.temp).time.hour
    tmin_hour = min(hours, key=lambda h: h.temp).time.hour
    for h in hours:
        hr = h.time.hour
        cx = x(hr)
        if hr % 3 == 0:
            s = 3.3
            parts.append(
                f'<g transform="translate({_f(cx - s / 2)} 0) scale({s / 24:.4f})" class="wx-icon">'
                f"{icon_paths(h.icon)}</g>"
            )
            parts.append(
                f'<text x="{_f(cx)}" y="{_f(height - 0.35)}" class="wx-hour">{hr:02d}</text>'
            )
        if hr % 3 == 0 or hr in (tmax_hour, tmin_hour):
            strong = hr in (tmax_hour, tmin_hour)
            parts.append(
                f'<circle cx="{_f(cx)}" cy="{_f(y(h.temp))}" r="{0.62 if strong else 0.45}" '
                f'class="wx-dot{" strong" if strong else ""}"/>'
            )
            if hr % 3 == 0 or strong:
                parts.append(
                    f'<text x="{_f(cx)}" y="{_f(y(h.temp) - 1.25)}" class="wx-temp'
                    f'{" strong" if strong else ""}">{round(h.temp)}°</text>'
                )
    parts.append(f'<text x="0" y="{_f(rain_base - rain_h + 1.2)}" class="wx-note">rain mm/h</text>')
    return (
        f'<svg class="wx-chart" viewBox="0 0 {_f(width)} {_f(height)}" width="{_f(width)}mm" '
        f'height="{_f(height)}mm">{"".join(parts)}</svg>'
    )


def range_rows(days: list[Day]) -> list[dict[str, Any]]:
    if not days:
        return []
    lo = min(d.tmin for d in days)
    hi = max(d.tmax for d in days)
    span = max(1.0, hi - lo)
    return [
        {
            "day": d,
            "abbr": DAY_ABBR[d.date.weekday()],
            "left": (d.tmin - lo) / span * 100,
            "width": max(3.0, (d.tmax - d.tmin) / span * 100),
            "weekend": d.date.weekday() >= 5,
            "typical": d.typical,
        }
        for d in days
    ]


@module("weather", title="Weather", icon="cloud-sun", color="weather")
def weather_page(data: Data, page: PageCtx) -> dict[str, Any]:
    fc = data.forecast
    width = data.sheet.panel_w - 10
    ctx: dict[str, Any] = {"meta": data.place_label, "fc": fc, "normals": data.normals}
    if data.is_trip:
        days = trip_days(data)
        if not days:
            ctx["missing"] = True
            return ctx
        ctx |= {
            "view": "range",
            "rows": range_rows(days),
            "advice": advice(days),
            "first": days[0] if days else None,
            "last": days[-1] if days else None,
            "phases": astro.key_phases(data.start, data.end, data.tz),
            "too_far": not days,
            "has_typical": any(d.typical for d in days),
        }
        return ctx
    if fc is None:
        ctx["missing"] = True
        return ctx
    if data.edition == "daily":
        today = fc.day(data.date)
        if today is None:
            ctx["missing"] = True
            return ctx
        feels = [h.feels for h in today.hours if 7 <= h.time.hour <= 22] or [today.tmin]
        ctx |= {
            "view": "day",
            "today": today,
            "feels": (min(feels), max(feels)),
            "chart": hourly_svg(today.hours, width),
            "advice": advice([today]),
            "next": [d for d in fc.days if d.date > data.date][:3],
            "moon": astro.moon(data.date),
        }
        return ctx
    if data.edition == "weekly":
        days = fc.between(data.start, data.end)
        ctx |= {
            "view": "range",
            "rows": range_rows(days),
            "advice": advice(days),
            "phases": astro.key_phases(data.start, data.end, data.tz),
            "first": days[0] if days else None,
            "last": days[-1] if days else None,
        }
        return ctx
    # monthly: the next two weeks of forecast plus the month's climate normals
    days = [d for d in fc.days if d.date >= data.date][:14]
    ctx |= {
        "view": "range",
        "compact": True,
        "rows": range_rows(days),
        "advice": [],
        "phases": astro.key_phases(data.start, data.end, data.tz),
        "first": fc.day(data.start),
        "last": fc.day(data.end),
        "outlook_note": f"Forecast from {d_short(days[0].date)}" if days else "",
    }
    return ctx
