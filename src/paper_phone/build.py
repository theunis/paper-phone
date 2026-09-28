"""Gather everything a booklet needs (mode-independent), before any HTML is made."""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any
from zoneinfo import ZoneInfo

from paper_phone.config import Config, Edition, MapSpec, PageSpec, Place, Task
from paper_phone.http import Http
from paper_phone.layout import Box, Sheet, back_boxes
from paper_phone.maps.osm import Frame, MapData, fetch
from paper_phone.maps.render import Marker
from paper_phone.sources import agenda, content, weather
from paper_phone.sources.geo import Geo, geocode

DEFAULT_PAGES: dict[Edition, list[PageSpec]] = {
    "daily": [
        "cover",
        "agenda",
        "weather",
        "tasks",
        "training",
        ["words", "sudoku"],
        "recipe",
        "notes",
    ],
    "weekly": [
        "cover",
        "week",
        "weather",
        "tasks",
        "training",
        "recipe",
        ["words", "prompts"],
        "habits",
    ],
    "monthly": ["cover", "calendar", "weather", "tasks", "training", "words", "recipe", "habits"],
    "travel": [
        "cover",
        "itinerary",
        "weather",
        "phrases",
        "practical",
        "packing",
        "places",
        "expenses",
    ],
}


@dataclass
class ResolvedMap:
    key: str
    title: str
    subtitle: str | None
    box: Box
    frame: Frame
    data: MapData | None
    detail: bool
    markers: list[Marker]
    focus: tuple[float, float] | None


@dataclass
class Data:
    cfg: Config
    edition: Edition
    date: dt.date
    start: dt.date
    end: dt.date
    sheet: Sheet
    pages: list[PageSpec]
    generated: dt.datetime
    place: Geo | None = None  # where the weather and maps are centred
    place_label: str = ""
    home: Geo | None = None
    tz: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Amsterdam"))
    home_tz: ZoneInfo | None = None
    forecast: weather.Forecast | None = None
    normals: weather.Normals | None = None
    items: list[agenda.Item] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    country: dict[str, Any] = field(default_factory=dict)
    home_country: dict[str, Any] = field(default_factory=dict)
    rate: float | None = None
    stay: Geo | None = None
    places: list[tuple[Place, Geo]] = field(default_factory=list)
    maps: list[ResolvedMap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)  # module scratch space

    @property
    def days(self) -> list[dt.date]:
        return [self.start + dt.timedelta(days=i) for i in range((self.end - self.start).days + 1)]

    @property
    def index(self) -> int:
        """A counter for 'of the day/week/month' picks."""
        if self.edition == "weekly":
            return self.date.isocalendar()[1] + 53 * self.date.year
        if self.edition == "monthly":
            return self.date.month + 12 * self.date.year
        return self.date.toordinal()

    def items_on(self, day: dt.date) -> list[agenda.Item]:
        return [i for i in self.items if i.date == day]

    @property
    def is_trip(self) -> bool:
        return self.edition == "travel"


def date_range(edition: Edition, date: dt.date, cfg: Config) -> tuple[dt.date, dt.date]:
    if edition == "weekly":
        start = date - dt.timedelta(days=date.weekday())
        return start, start + dt.timedelta(days=6)
    if edition == "monthly":
        start = date.replace(day=1)
        nxt = (start + dt.timedelta(days=32)).replace(day=1)
        return start, nxt - dt.timedelta(days=1)
    if edition == "travel":
        if cfg.trip is None:
            raise ValueError("The travel edition needs a `trip:` section in the config")
        return cfg.trip.start, cfg.trip.end
    return date, date


def _try[T](data: Data, what: str, fn: Callable[[], T]) -> T | None:
    try:
        return fn()
    except Exception as exc:  # network trouble must never kill a print run
        data.warnings.append(f"{what}: {exc}")
        return None


def _haversine(a: Geo, b: Geo) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    return 2 * 6371000 * math.asin(math.sqrt(h))


def gather(cfg: Config, edition: Edition, date: dt.date, http: Http, *, maps: bool = True) -> Data:
    start, end = date_range(edition, date, cfg)
    anchor = start if edition == "travel" else date
    pages = list(cfg.pages.get(edition) or DEFAULT_PAGES[edition])
    if len(pages) != 8:
        raise ValueError(f"The {edition} edition needs exactly 8 pages, got {len(pages)}")
    data = Data(
        cfg=cfg,
        edition=edition,
        date=anchor,
        start=start,
        end=end,
        sheet=Sheet(cfg.paper),
        pages=pages,
        generated=dt.datetime.now().replace(microsecond=0),
    )

    data.home = _try(data, "Geocoding home", lambda: geocode(http, cfg.home))
    trip = cfg.trip if edition == "travel" else None
    if trip:
        data.place = _try(
            data, "Geocoding destination", lambda: geocode(http, Place(query=trip.destination))
        )
        data.place_label = trip.destination.split(",")[0]
        if trip.stay:
            data.stay = _try(data, "Geocoding stay", partial(geocode, http, trip.stay))
        for p in trip.places:
            geo = _try(data, f"Geocoding {p.label}", partial(geocode, http, p))
            if geo:
                data.places.append((p, geo))
    else:
        data.place = data.home
        data.place_label = (data.home.city if data.home else None) or cfg.home.label

    place = data.place
    if place:
        data.forecast = _try(
            data, "Weather forecast", partial(weather.forecast, http, place.lat, place.lon)
        )
        if data.forecast:
            data.tz = ZoneInfo(data.forecast.timezone)
        needs_normals = edition == "monthly" or (
            edition == "travel" and (data.forecast is None or data.forecast.day(end) is None)
        )
        if needs_normals:
            data.normals = _try(
                data,
                "Climate normals",
                partial(weather.normals, http, place.lat, place.lon, start, end),
            )
    home = data.home
    if trip and home:
        home_fc = _try(data, "Home time zone", partial(weather.forecast, http, home.lat, home.lon))
        if home_fc:
            data.home_tz = ZoneInfo(home_fc.timezone)

    # Agenda: calendars, config events, public holidays, trip legs.
    country_code = (data.place.country_code if data.place else None) or cfg.country
    if trip and not trip.include_calendars:
        items = [
            agenda.Item(ev.date, ev.start, ev.end, ev.title, ev.location)
            for ev in cfg.events
            if start <= ev.date <= end
        ]
    else:
        read = partial(agenda.calendar_items, http, cfg, start, end, data.tz)
        items = _try(data, "Calendars", read) or []
    items += agenda.holiday_items(country_code if trip else cfg.country, start, end)
    if trip:
        for leg in trip.transport:
            when = None
            if leg.time:
                hh, mm = (int(x) for x in leg.time.split(":")[:2])
                when = dt.time(hh, mm)
            items.append(agenda.Item(leg.date, when, None, leg.title, leg.detail, kind="transport"))
        for day, entries in trip.itinerary.items():
            items += [agenda.Item(day, title=e, kind="plan") for e in entries]
    data.items = sorted(items, key=lambda i: i.sort_key)
    data.tasks = _try(data, "Tasks", partial(agenda.load_tasks, cfg)) or []

    facts = content.countries()
    data.country = facts.get(country_code, {})
    home_code = (data.home.country_code if data.home else None) or cfg.country
    data.home_country = facts.get(home_code, {})
    if trip:
        quote = trip.currency or data.country.get("currency")
        base = data.home_country.get("currency", "EUR")
        if quote:
            data.rate = _try(
                data, "Exchange rate", lambda: content.exchange_rate(http, base, quote)
            )

    if maps and cfg.back != "blank":
        data.maps = _resolve_maps(data, http)
    return data


def _default_specs(data: Data) -> list[MapSpec]:
    cfg = data.cfg
    if data.is_trip:
        specs = [
            MapSpec(title=data.place_label, place="fit" if data.places else "city", scale=12000)
        ]
        specs.append(
            MapSpec(
                title="Around your stay" if data.stay else "Old town",
                place="stay" if data.stay else "city",
                scale=6500,
            )
        )
        if data.places:
            far = max(
                data.places,
                key=lambda pg: _haversine(pg[1], data.stay or data.place) if data.place else 0,
            )
            specs.append(MapSpec(title=far[0].label, place=far[0], scale=6500))
        else:
            specs.append(MapSpec(title=f"{data.place_label} centre", place="city", scale=4500))
        return specs
    specs = [MapSpec(title=f"{data.place_label} centre", place="city", scale=12000)]
    specs.append(MapSpec(title="Around home", place="home", scale=6500))
    if cfg.work:
        specs.append(MapSpec(title="Around work", place="work", scale=6500))
    else:
        specs.append(MapSpec(title="Old town", place="city", scale=5000))
    return specs


def _fit(points: list[Geo], box: Box, min_scale: int) -> tuple[Geo | None, int]:
    """Centre and scale that fit every point in the box, with a margin."""
    if not points:
        return None, min_scale
    lats = [p.lat for p in points]
    lons = [p.lon for p in points]
    lat0 = (min(lats) + max(lats)) / 2
    lon0 = (min(lons) + max(lons)) / 2
    dy = math.radians(max(lats) - min(lats)) * 6371000
    dx = math.radians(max(lons) - min(lons)) * 6371000 * math.cos(math.radians(lat0))
    needed = max(dx * 1000 / (box.w * 0.82), dy * 1000 / (box.h * 0.72))
    scale = max(min_scale, math.ceil(needed / 500) * 500)
    ref = points[0]
    centre = Geo(ref.name, lat0, lon0, ref.country_code, ref.city, None, ref.display)
    return centre, min(scale, 30000)


def _resolve_maps(data: Data, http: Http) -> list[ResolvedMap]:
    cfg = data.cfg
    boxes = back_boxes(data.sheet, cfg.back).maps
    specs = cfg.maps or _default_specs(data)
    city_geo = None
    home = data.home
    if cfg.city:
        city_geo = _try(data, "Geocoding city", partial(geocode, http, cfg.city))
    elif data.is_trip:
        city_geo = data.place
    elif home and home.city:
        query = Place(query=f"{home.city}, {home.country_code}")
        city_geo = _try(data, "Geocoding city centre", partial(geocode, http, query))
    city_geo = city_geo or data.place
    work_geo = None
    if cfg.work and not data.is_trip:
        work_geo = _try(data, "Geocoding work", partial(geocode, http, cfg.work))

    def where(p: str | Place) -> Geo | None:
        if isinstance(p, Place):
            return _try(data, f"Geocoding {p.label}", partial(geocode, http, p))
        return {
            "home": data.home,
            "work": work_geo,
            "stay": data.stay,
            "city": city_geo,
        }.get(p)

    markers: list[tuple[Geo, Marker]] = []
    if data.home and not data.is_trip:
        markers.append((data.home, Marker(data.home.lat, data.home.lon, "home", "Home")))
    if work_geo and not data.is_trip:
        markers.append((work_geo, Marker(work_geo.lat, work_geo.lon, "work", "Work")))
    if data.stay:
        markers.append((data.stay, Marker(data.stay.lat, data.stay.lon, "stay", "Stay")))
    for n, (place, geo) in enumerate(data.places, start=1):
        markers.append((geo, Marker(geo.lat, geo.lon, "place", place.label, number=n)))

    resolved = []
    for i, (spec, box) in enumerate(zip(specs, boxes, strict=False)):
        scale = spec.scale
        if spec.place == "fit":
            points = [g for g, _ in markers] + ([city_geo] if city_geo else [])
            geo, scale = _fit(points, box, spec.scale)
        else:
            geo = where(spec.place)
        if geo is None:
            data.warnings.append(f"Map {spec.title!r}: location unknown")
            continue
        if cfg.back == "poster":
            scale = max(scale, 15000)
        frame = Frame(geo.lat, geo.lon, scale, box.w, box.h)
        detail = scale <= 9000
        map_data = _try(
            data, f"Map data for {spec.title}", lambda f=frame, d=detail: fetch(http, f, d)
        )
        focus = frame.to_mm(geo.lon, geo.lat) if spec.place in ("home", "stay", "work") else None
        resolved.append(
            ResolvedMap(
                key=f"m{i}",
                title=spec.title,
                subtitle=None,
                box=box,
                frame=frame,
                data=map_data,
                detail=detail,
                markers=[m for _, m in markers],
                focus=focus,
            )
        )
    return resolved
