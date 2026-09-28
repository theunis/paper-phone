"""Moon phases, computed locally (accurate to within a few hours, plenty for paper)."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

SYNODIC = 29.530588853
# A reference new moon: 2000-01-06 18:14 UTC
_EPOCH = dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.UTC)

PHASES = [
    "New moon",
    "Waxing crescent",
    "First quarter",
    "Waxing gibbous",
    "Full moon",
    "Waning gibbous",
    "Last quarter",
    "Waning crescent",
]


@dataclass(frozen=True)
class Moon:
    age: float  # days since new moon
    illumination: float  # 0..1

    @property
    def fraction(self) -> float:
        return self.age / SYNODIC

    @property
    def waxing(self) -> bool:
        return self.fraction < 0.5

    @property
    def name(self) -> str:
        return PHASES[round(self.fraction * 8) % 8]


def moon(when: dt.datetime | dt.date) -> Moon:
    if not isinstance(when, dt.datetime):
        when = dt.datetime.combine(when, dt.time(21, 0), tzinfo=dt.UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    days = (when - _EPOCH).total_seconds() / 86400
    age = days % SYNODIC
    illumination = (1 - math.cos(2 * math.pi * age / SYNODIC)) / 2
    return Moon(age=age, illumination=illumination)


_PHASE_NAMES = ("New moon", "First quarter", "Full moon", "Last quarter")


def _phase_jde(k: float) -> float:
    """Julian ephemeris day of a principal moon phase (Meeus, ch. 49).

    k is integral for new moons; +0.25, +0.5, +0.75 for the other phases.
    Accurate to a few minutes, far better than a paper booklet needs.
    """
    t = k / 1236.85
    jde = (
        2451550.09766
        + 29.530588861 * k
        + 0.00015437 * t**2
        - 0.000000150 * t**3
        + 0.00000000073 * t**4
    )
    e = 1 - 0.002516 * t - 0.0000074 * t**2
    rad = math.radians
    m = rad(2.5534 + 29.10535670 * k - 0.0000014 * t**2 - 0.00000011 * t**3)
    mp = rad(
        201.5643 + 385.81693528 * k + 0.0107582 * t**2 + 0.00001238 * t**3 - 0.000000058 * t**4
    )
    f = rad(160.7108 + 390.67050284 * k - 0.0016118 * t**2 - 0.00000227 * t**3)
    om = rad(124.7746 - 1.56375588 * k + 0.0020672 * t**2 + 0.00000215 * t**3)
    sin = math.sin
    phase = round((k % 1) * 4) % 4
    if phase in (0, 2):
        new = phase == 0
        corr = (
            (-0.40720 if new else -0.40614) * sin(mp)
            + (0.17241 if new else 0.17302) * e * sin(m)
            + (0.01608 if new else 0.01614) * sin(2 * mp)
            + (0.01039 if new else 0.01043) * sin(2 * f)
            + (0.00739 if new else 0.00734) * e * sin(mp - m)
            - (0.00514 if new else 0.00515) * e * sin(mp + m)
            + (0.00208 if new else 0.00209) * e * e * sin(2 * m)
            - 0.00111 * sin(mp - 2 * f)
            - 0.00057 * sin(mp + 2 * f)
            + 0.00056 * e * sin(2 * mp + m)
            - 0.00042 * sin(3 * mp)
            + 0.00042 * e * sin(m + 2 * f)
            + 0.00038 * e * sin(m - 2 * f)
            - 0.00024 * e * sin(2 * mp - m)
            - 0.00017 * sin(om)
        )
    else:
        corr = (
            -0.62801 * sin(mp)
            + 0.17172 * e * sin(m)
            - 0.01183 * e * sin(mp + m)
            + 0.00862 * sin(2 * mp)
            + 0.00804 * sin(2 * f)
            + 0.00454 * e * sin(mp - m)
            + 0.00204 * e * e * sin(2 * m)
            - 0.00180 * sin(mp - 2 * f)
            - 0.00070 * sin(mp + 2 * f)
            - 0.00040 * sin(3 * mp)
            - 0.00034 * e * sin(2 * mp - m)
            + 0.00032 * e * sin(m + 2 * f)
            + 0.00032 * e * sin(m - 2 * f)
            - 0.00028 * e * e * sin(mp + 2 * m)
            + 0.00027 * e * sin(2 * mp + m)
            - 0.00017 * sin(om)
        )
        w = (
            0.00306
            - 0.00038 * e * math.cos(m)
            + 0.00026 * math.cos(mp)
            - 0.00002 * math.cos(mp - m)
            + 0.00002 * math.cos(mp + m)
            + 0.00002 * math.cos(2 * f)
        )
        corr += w if phase == 1 else -w
    return jde + corr


def _jd_to_datetime(jd: float) -> dt.datetime:
    return dt.datetime.fromtimestamp((jd - 2440587.5) * 86400, tz=dt.UTC)


def phase_times(
    start: dt.date, end: dt.date, tz: dt.tzinfo = dt.UTC
) -> list[tuple[dt.datetime, str]]:
    """New, first-quarter, full and last-quarter moons whose local date is in [start, end]."""
    years = start.year + (start.timetuple().tm_yday - 1) / 365.25 - 2000
    k0 = math.floor(years * 12.3685) - 1
    out = []
    k = float(k0)
    while True:
        for quarter in range(4):
            when = _jd_to_datetime(_phase_jde(k + quarter / 4)).astimezone(tz)
            if when.date() > end:
                return out
            if when.date() >= start:
                out.append((when, _PHASE_NAMES[quarter]))
        k += 1


def key_phases(start: dt.date, end: dt.date, tz: dt.tzinfo = dt.UTC) -> list[tuple[dt.date, str]]:
    """Dates of the principal moon phases in [start, end] (local dates in `tz`)."""
    return [(when.date(), name) for when, name in phase_times(start, end, tz)]


def moon_svg(
    m: Moon, size: float = 10, *, dark: str = "currentColor", lit: str = "var(--moon, #f4e7b0)"
) -> str:
    """A small moon glyph: lit part is paper, shadow is filled."""
    r = size / 2
    f = m.fraction
    # Terminator: an ellipse with horizontal radius |cos(2*pi*f)| * r
    k = math.cos(2 * math.pi * f)
    rx = abs(k) * r
    # Shadow path: outer semicircle on the dark side + terminator back.
    if m.waxing:
        # dark on the left
        outer = f"M{r},0 A{r},{r} 0 0 0 {r},{size}"
        sweep = 0 if k > 0 else 1
    else:
        outer = f"M{r},0 A{r},{r} 0 0 1 {r},{size}"
        sweep = 1 if k > 0 else 0
    terminator = f"A{rx:.3f},{r} 0 0 {sweep} {r},0"
    return (
        f'<svg class="moon" viewBox="0 0 {size} {size}" width="{size}mm" height="{size}mm">'
        f'<circle cx="{r}" cy="{r}" r="{r - 0.25}" fill="{lit}" stroke="{dark}" '
        f'stroke-width="0.5"/>'
        f'<path d="{outer} {terminator} Z" fill="{dark}"/></svg>'
    )


def sun_times(
    day: dt.date, lat: float, lon: float, tz: dt.tzinfo
) -> tuple[dt.datetime, dt.datetime] | None:
    """Sunrise and sunset (local time) from the standard sunrise equation, ±1-2 min.

    Returns None during polar day or night.
    """
    n = math.ceil(day.toordinal() + 1721424.5 - 2451545.0 + 0.0008)
    j_star = n - lon / 360
    m = math.radians((357.5291 + 0.98560028 * j_star) % 360)
    c = 1.9148 * math.sin(m) + 0.02 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
    lam = math.radians((math.degrees(m) + c + 180 + 102.9372) % 360)
    transit = 2451545.0 + j_star + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam)
    decl = math.asin(math.sin(lam) * math.sin(math.radians(23.4397)))
    phi = math.radians(lat)
    cos_w = (math.sin(math.radians(-0.833)) - math.sin(phi) * math.sin(decl)) / (
        math.cos(phi) * math.cos(decl)
    )
    if not -1 <= cos_w <= 1:
        return None
    w = math.degrees(math.acos(cos_w)) / 360

    def to_dt(jd: float) -> dt.datetime:
        return dt.datetime.fromtimestamp((jd - 2440587.5) * 86400, tz=dt.UTC).astimezone(tz)

    return to_dt(transit - w), to_dt(transit + w)


def clock_changes(start: dt.date, end: dt.date, tz: dt.tzinfo) -> list[tuple[dt.date, float]]:
    """Days in [start, end] on which the UTC offset changes, with the shift in hours."""
    out = []
    day = start
    while day <= end:
        before = dt.datetime.combine(day, dt.time(0, 30), tzinfo=tz).utcoffset()
        after = dt.datetime.combine(day, dt.time(23, 30), tzinfo=tz).utcoffset()
        if before is not None and after is not None and before != after:
            out.append((day, (after - before).total_seconds() / 3600))
        day += dt.timedelta(days=1)
    return out
