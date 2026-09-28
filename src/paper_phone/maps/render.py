"""Render OpenStreetMap data as a print-first SVG map (all units in millimetres).

Colour and black-and-white are separate styles, not a desaturated copy: the
b&w style swaps fills for patterns (hatched water, dotted parks) and leans on
casing weight to rank roads.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass, field
from typing import Any, Literal

from shapely import LineString, MultiLineString, Point, Polygon, box, ops
from shapely.geometry.base import BaseGeometry

from paper_phone.icons import icon_paths
from paper_phone.maps.osm import Area, Frame, MapData, Pt

Mode = Literal["color", "bw"]

STYLES: dict[str, dict[str, str]] = {
    "color": {
        "land": "#f7f5ef",
        "building": "#e0d9cd",
        "water": "#b3d4ea",
        "water_line": "#b3d4ea",
        "water_text": "#2c6a97",
        "park": "#d2e7c4",
        "forest": "#bddaa9",
        "grass": "#dcecd0",
        "pitch": "#cbe6c3",
        "cemetery": "#d4e0c8",
        "beach": "#f2e5bd",
        "green_text": "#3b7536",
        "casing": "#b0a595",
        "minor": "#ffffff",
        "service": "#ffffff",
        "pedestrian": "#f1ede4",
        "tertiary": "#fff3cc",
        "secondary": "#fde2a1",
        "primary": "#f9cd83",
        "trunk": "#f5ae83",
        "motorway": "#ee9a78",
        "path": "#a88e79",
        "rail": "#56524d",
        "tram": "#8b8079",
        "text": "#262626",
        "halo": "#ffffff",
        "place_text": "#6b5a4c",
        "grid": "#2a2a2a",
        "accent": "#d9482b",
        "home": "#1f1f1f",
    },
    "bw": {
        "land": "#ffffff",
        "building": "#e3e3e3",
        "water": "#e9e9e9",
        "water_line": "#b8b8b8",
        "water_text": "#303030",
        "park": "#f8f8f8",
        "forest": "#f0f0f0",
        "grass": "#fafafa",
        "pitch": "#f8f8f8",
        "cemetery": "#f5f5f5",
        "beach": "#fcfcfc",
        "green_text": "#303030",
        "casing": "#6e6e6e",
        "minor": "#ffffff",
        "service": "#ffffff",
        "pedestrian": "#f0f0f0",
        "tertiary": "#ffffff",
        "secondary": "#d9d9d9",
        "primary": "#c4c4c4",
        "trunk": "#aaaaaa",
        "motorway": "#999999",
        "path": "#6a6a6a",
        "rail": "#1e1e1e",
        "tram": "#4a4a4a",
        "text": "#111111",
        "halo": "#ffffff",
        "place_text": "#4d4d4d",
        "grid": "#000000",
        "accent": "#000000",
        "home": "#000000",
    },
}

# Black-and-white textures: (row spacing, dash pattern or None for solid lines,
# stroke width, grey). Drawn as clipped vector strokes, never SVG <pattern>s,
# which Chrome rasterises when printing.
BW_TEXTURE: dict[str, tuple[float, str | None, float, str]] = {
    "water": (0.95, None, 0.13, "#8c8c8c"),
    "park": (1.3, "0 1.3", 0.34, "#8a8a8a"),
    "pitch": (1.3, "0 1.3", 0.34, "#8a8a8a"),
    "grass": (1.7, "0 1.7", 0.3, "#9a9a9a"),
    "forest": (0.95, "0 0.95", 0.42, "#7a7a7a"),
    "cemetery": (1.5, "0.5 1", 0.14, "#8a8a8a"),
    "beach": (1.8, "0 1.8", 0.22, "#9a9a9a"),
}

ROAD_GROUP = {
    "motorway": "motorway",
    "motorway_link": "motorway",
    "trunk": "trunk",
    "trunk_link": "trunk",
    "primary": "primary",
    "primary_link": "primary",
    "secondary": "secondary",
    "secondary_link": "secondary",
    "tertiary": "tertiary",
    "tertiary_link": "tertiary",
    "unclassified": "minor",
    "residential": "minor",
    "living_street": "minor",
    "pedestrian": "pedestrian",
    "service": "service",
    "track": "path",
    "footway": "path",
    "cycleway": "path",
    "path": "path",
    "steps": "path",
    "bridleway": "path",
}
GROUP_ORDER = [
    "service",
    "minor",
    "pedestrian",
    "tertiary",
    "secondary",
    "primary",
    "trunk",
    "motorway",
]
WIDTH_DETAIL = {
    "path": 0.16,
    "service": 0.42,
    "minor": 0.85,
    "pedestrian": 0.85,
    "tertiary": 1.05,
    "secondary": 1.15,
    "primary": 1.25,
    "trunk": 1.35,
    "motorway": 1.45,
}
WIDTH_OVERVIEW = {
    "minor": 0.42,
    "pedestrian": 0.42,
    "service": 0.0,
    "tertiary": 0.72,
    "secondary": 0.86,
    "primary": 0.98,
    "trunk": 1.08,
    "motorway": 1.18,
}
LABEL_RANK = {
    "motorway": 5,
    "trunk": 5,
    "primary": 4,
    "secondary": 3,
    "tertiary": 2,
    "minor": 1,
    "pedestrian": 1,
    "service": 0,
    "path": 0,
}

# POI categories: (icon, colour, per-map cap, label on map)
POI_STYLE: dict[str, tuple[str, str, int, bool]] = {
    "station": ("train-front", "#1f1f1f", 6, True),
    "tram": ("tram-front", "#5a5a5a", 5, False),
    "museum": ("landmark", "#7d4e9e", 6, True),
    "attraction": ("star", "#c4561d", 6, True),
    "viewpoint": ("mountain", "#c4561d", 3, True),
    "supermarket": ("shopping-cart", "#2f6fb3", 4, False),
    "bakery": ("croissant", "#b8801f", 3, False),
    "cafe": ("coffee", "#8a5a35", 6, False),
    "restaurant": ("utensils", "#c2452f", 6, False),
    "bar": ("beer", "#a87a12", 3, False),
    "pharmacy": ("pill", "#1d9a5b", 3, False),
    "hospital": ("hospital", "#d0342c", 2, True),
    "atm": ("banknote", "#5f6b7a", 3, False),
    "police": ("shield", "#2f3c8f", 2, False),
    "post": ("mail", "#d09a00", 2, False),
    "library": ("book-open", "#6a4fa0", 2, False),
    "toilets": ("info", "#4b5563", 3, False),
    "water": ("droplet", "#2b7fb0", 3, False),
    "bike": ("bike", "#0f7a6e", 3, False),
    "market": ("shopping-cart", "#8a6d1f", 2, True),
}
POI_LABELS = {
    "station": "Station",
    "tram": "Tram stop",
    "museum": "Museum",
    "attraction": "Sight",
    "viewpoint": "Viewpoint",
    "supermarket": "Supermarket",
    "bakery": "Bakery",
    "cafe": "Café",
    "restaurant": "Restaurant",
    "bar": "Bar",
    "pharmacy": "Pharmacy",
    "hospital": "Hospital",
    "atm": "Cash",
    "police": "Police",
    "post": "Post",
    "library": "Library",
    "toilets": "Toilets",
    "water": "Drinking water",
    "bike": "Bike rental",
    "market": "Market",
}


@dataclass
class Marker:
    """Something the user placed on the map: home, stay, or a numbered place."""

    lat: float
    lon: float
    kind: Literal["home", "stay", "work", "place"]
    label: str
    number: int | None = None


@dataclass
class PlacedPoi:
    kind: str
    name: str | None
    ref: str
    distance_m: float

    @property
    def walk_min(self) -> int:
        return max(1, round(self.distance_m * 1.25 / 80))

    @property
    def label(self) -> str:
        return POI_LABELS.get(self.kind, self.kind)

    @property
    def icon(self) -> str:
        return POI_STYLE[self.kind][0]


@dataclass
class MapResult:
    svg: str
    title: str
    frame: Frame
    cols: int
    rows: int
    number: int = 1
    box: Any = None  # where it sits on the sheet (layout.Box)
    pois: list[PlacedPoi] = field(default_factory=list)
    marker_refs: dict[str, str] = field(default_factory=dict)

    def locate(self, lon: float, lat: float) -> str | None:
        """'2 · C3': map number and grid square, if the point is on this map."""
        ref = self.ref_lonlat(lon, lat)
        return f"{self.number} · {ref}" if ref else None

    def ref(self, x: float, y: float) -> str:
        col = min(self.cols - 1, max(0, int(x / (self.frame.width / self.cols))))
        row = min(self.rows - 1, max(0, int(y / (self.frame.height / self.rows))))
        return f"{chr(65 + col)}{row + 1}"

    def ref_lonlat(self, lon: float, lat: float) -> str | None:
        x, y = self.frame.to_mm(lon, lat)
        if 0 <= x <= self.frame.width and 0 <= y <= self.frame.height:
            return self.ref(x, y)
        return None


# ---------------------------------------------------------------- helpers


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _path(coords: list[Pt], close: bool = False) -> str:
    if not coords:
        return ""
    head, *rest = coords
    d = f"M{_f(head[0])} {_f(head[1])}" + "".join(f"L{_f(x)} {_f(y)}" for x, y in rest)
    return d + ("Z" if close else "")


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


_NARROW = set("iljtfrI.,:;'!|()[] ")
_WIDE = set("mwMW@")


def text_width(text: str, size: float, letter_spacing: float = 0.0) -> float:
    """Rough advance width of Inter Tight text, in the same unit as `size`."""
    total = 0.0
    for ch in text:
        if ch in _NARROW:
            total += 0.27
        elif ch in _WIDE:
            total += 0.82
        elif ch.isupper() or ch.isdigit():
            total += 0.62
        else:
            total += 0.52
    return total * size + letter_spacing * max(0, len(text) - 1)


class Placer:
    """Greedy label collision detection."""

    def __init__(self, width: float, height: float, margin: float = 1.2):
        self.area = box(margin, margin, width - margin, height - margin)
        self.taken: list[BaseGeometry] = []

    def free(self, shape: BaseGeometry) -> bool:
        if not self.area.contains(shape):
            return False
        minx, miny, maxx, maxy = shape.bounds
        for other in self.taken:
            ox0, oy0, ox1, oy1 = other.bounds
            if ox0 > maxx or ox1 < minx or oy0 > maxy or oy1 < miny:
                continue
            if other.intersects(shape):
                return False
        return True

    def take(self, shape: BaseGeometry) -> None:
        self.taken.append(shape)

    def try_take(self, shape: BaseGeometry) -> bool:
        if self.free(shape):
            self.take(shape)
            return True
        return False


def _turning(line: LineString) -> tuple[float, float]:
    """(total, max single) absolute turning angle in degrees along a polyline."""
    pts = list(line.coords)
    total = biggest = 0.0
    for (x0, y0), (x1, y1), (x2, y2) in zip(pts, pts[1:], pts[2:], strict=False):
        a = math.atan2(y1 - y0, x1 - x0)
        b = math.atan2(y2 - y1, x2 - x1)
        turn = abs((math.degrees(b - a) + 180) % 360 - 180)
        total += turn
        biggest = max(biggest, turn)
    return total, biggest


def _lines(geom: BaseGeometry) -> list[LineString]:
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, LineString)]


def _nice_distance(target_m: float) -> int:
    steps = [20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000]
    return min(steps, key=lambda s: abs(math.log(s / target_m)))


# ---------------------------------------------------------------- renderer


class MapRenderer:
    def __init__(
        self,
        data: MapData,
        frame: Frame,
        *,
        mode: Mode,
        detail: bool,
        prefix: str,
        title: str,
        subtitle: str | None = None,
        markers: list[Marker] | None = None,
        focus: tuple[float, float] | None = None,
        cell_mm: float = 24.0,
        show_pois: bool = True,
        number: int | None = None,
    ):
        self.d = data
        self.frame = frame
        self.mode = mode
        self.detail = detail
        self.p = prefix
        self.title = title
        self.subtitle = subtitle
        self.markers = markers or []
        self.focus = focus
        self.show_pois = show_pois
        self.s = dict(STYLES[mode])
        self.W, self.H = frame.width, frame.height
        self.cols = max(2, round(self.W / cell_mm))
        self.rows = max(2, round(self.H / cell_mm))
        self.placer = Placer(self.W, self.H)
        self.clip = box(-2, -2, self.W + 2, self.H + 2)
        self.number = number
        self.result = MapResult("", title, frame, self.cols, self.rows, number=number or 1)

    # -- layers -------------------------------------------------------

    def _paint(self, rings: list[list[Pt]], kind: str) -> str:
        """Fill shapes; in black-and-white also lay a vector texture over them.

        Texture rows only span each shape's bounding box: Chrome turns every dash
        into its own PDF path, so full-width rows would bloat the file.
        """
        d = "".join(_path(r, close=True) for r in rings)
        out = f'<path d="{d}" fill="{self.s[kind]}" fill-rule="evenodd"/>'
        texture = BW_TEXTURE.get(kind) if self.mode == "bw" else None
        if texture is None or not rings:
            return out
        step, dash, width, grey = texture
        spans: dict[int, list[tuple[float, float]]] = {}
        for ring in rings:
            xs = [x for x, _ in ring]
            ys = [y for _, y in ring]
            x0, x1 = max(min(xs), -1.0), min(max(xs), self.W + 1)
            y0, y1 = max(min(ys), -1.0), min(max(ys), self.H + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            for row in range(math.floor(y0 / step), math.ceil(y1 / step) + 1):
                spans.setdefault(row, []).append((x0, x1))
        parts = []
        for row, intervals in sorted(spans.items()):
            offset = step / 2 if row % 2 else 0.0
            intervals.sort()
            merged = [list(intervals[0])]
            for a, b in intervals[1:]:
                if a <= merged[-1][1] + step:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            for a, b in merged:
                start = math.floor((a - offset) / step) * step + offset  # stay on one grid
                parts.append(f"M{_f(start)} {_f(row * step)}H{_f(b + step)}")
        if not parts:
            return out
        self._clip_id += 1
        cid = f"{self.p}-t{self._clip_id}"
        self.defs.append(f'<clipPath id="{cid}"><path d="{d}" clip-rule="evenodd"/></clipPath>')
        dash_attr = f' stroke-dasharray="{dash}" stroke-linecap="round"' if dash else ""
        return out + (
            f'<g clip-path="url(#{cid})"><path d="{"".join(parts)}" fill="none" '
            f'stroke="{grey}" stroke-width="{width}"{dash_attr}/></g>'
        )

    def _areas(self, areas: list[Area], fill_key: str | None = None) -> str:
        by_kind: dict[str, list[list[Pt]]] = {}
        for area in areas:
            by_kind.setdefault(fill_key or area.kind, []).extend(area.rings)
        return "".join(self._paint(rings, kind) for kind, rings in by_kind.items())

    def _sea(self) -> str:
        """Close coastline ways against the frame and fill the sea side."""
        if not self.d.coastline:
            return ""
        frame = box(-3, -3, self.W + 3, self.H + 3)
        lines = [LineString(c.coords) for c in self.d.coastline if len(c.coords) >= 2]
        merged = ops.linemerge(MultiLineString(lines))
        clipped = _lines(merged.intersection(frame))
        if not clipped:
            return ""
        faces = list(ops.polygonize(ops.unary_union([*clipped, frame.exterior])))
        water = []
        for face in faces:
            probe = face.representative_point()
            nearest_line = min(clipped, key=lambda ln: ln.distance(probe))
            s = nearest_line.project(probe)
            a = nearest_line.interpolate(max(0, s - 0.05))
            b = nearest_line.interpolate(min(nearest_line.length, s + 0.05))
            dx, dy = b.x - a.x, b.y - a.y
            n = math.hypot(dx, dy) or 1
            # OSM coastlines keep land on the left; in y-down paper coordinates the
            # water side of direction (dx, dy) is (-dy, dx).
            mid = nearest_line.interpolate(s)
            test = Point(mid.x - dy / n * 0.2, mid.y + dx / n * 0.2)
            if face.buffer(0.01).contains(test):
                water.append(face)
        rings = [list(face.exterior.coords) for face in water if isinstance(face, Polygon)]
        if not rings:
            return ""
        return self._paint(rings, "water")

    def _buildings(self) -> str:
        if not self.d.buildings:
            return ""
        tol = 0.06 if self.detail else 0.1
        parts = []
        for ring in self.d.buildings:
            xs = [x for x, _ in ring]
            ys = [y for _, y in ring]
            if max(xs) < -2 or min(xs) > self.W + 2 or max(ys) < -2 or min(ys) > self.H + 2:
                continue
            if len(ring) > 5:
                simple = LineString(ring).simplify(tol)
                ring = list(simple.coords)
            parts.append(_path(ring, close=True))
        return f'<path d="{"".join(parts)}" fill="{self.s["building"]}"/>'

    def _roads(self) -> str:
        widths = WIDTH_DETAIL if self.detail else WIDTH_OVERVIEW
        grouped: dict[str, list[str]] = {}
        for road in self.d.roads:
            if road.tunnel:
                continue
            group = ROAD_GROUP.get(road.kind)
            if group is None or widths.get(group, 0) <= 0:
                continue
            grouped.setdefault(group, []).append(_path(road.coords))
        out = []
        if "path" in grouped:
            out.append(
                f'<path d="{"".join(grouped["path"])}" fill="none" stroke="{self.s["path"]}" '
                f'stroke-width="{widths["path"]}" stroke-dasharray=".6 .35" '
                'stroke-linecap="butt"/>'
            )
        casing_extra = 0.3 if self.detail else 0.24
        for group in GROUP_ORDER:
            if group in grouped:
                w = widths[group] + casing_extra
                out.append(
                    f'<path d="{"".join(grouped[group])}" fill="none" stroke="{self.s["casing"]}" '
                    f'stroke-width="{_f(w)}" stroke-linecap="round" stroke-linejoin="round"/>'
                )
        for group in GROUP_ORDER:
            if group in grouped:
                out.append(
                    f'<path d="{"".join(grouped[group])}" fill="none" stroke="{self.s[group]}" '
                    f'stroke-width="{_f(widths[group])}" stroke-linecap="round" '
                    'stroke-linejoin="round"/>'
                )
        return "".join(out)

    def _rails(self) -> str:
        rail = [
            _path(r.coords)
            for r in self.d.rails
            if r.kind != "tram" and not r.tunnel and not r.service
        ]
        tram = [_path(r.coords) for r in self.d.rails if r.kind == "tram" and not r.tunnel]
        out = []
        if rail and not self.detail:
            out.append(
                f'<path d="{"".join(rail)}" fill="none" stroke="{self.s["rail"]}" '
                'stroke-width=".32" stroke-opacity=".75"/>'
            )
        elif rail:
            d = "".join(rail)
            out.append(f'<path d="{d}" fill="none" stroke="{self.s["rail"]}" stroke-width=".55"/>')
            out.append(
                f'<path d="{d}" fill="none" stroke="#fff" stroke-width=".28" '
                'stroke-dasharray="1.4 1.4"/>'
            )
        if tram and self.detail:
            out.append(
                f'<path d="{"".join(tram)}" fill="none" stroke="{self.s["tram"]}" '
                'stroke-width=".2"/>'
            )
        return "".join(out)

    def _waterways(self) -> str:
        width = {"river": 1.4, "canal": 0.9 if self.detail else 0.6, "stream": 0.35}
        out = []
        for ww in self.d.waterways:
            if ww.tunnel:
                continue
            out.append(
                f'<path d="{_path(ww.coords)}" fill="none" stroke="{self.s["water_line"]}" '
                f'stroke-width="{width[ww.kind]}" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        return "".join(out)

    # -- symbols ------------------------------------------------------

    def _icon(self, name: str, cx: float, cy: float, size: float, color: str) -> str:
        scale = size / 24
        return (
            f'<g transform="translate({_f(cx - size / 2)} {_f(cy - size / 2)}) scale({scale:.4f})" '
            f'fill="none" stroke="{color}" stroke-width="2.6" stroke-linecap="round" '
            f'stroke-linejoin="round">{icon_paths(name)}</g>'
        )

    def _markers(self) -> str:
        out = []
        for m in self.markers:
            x, y = self.frame.to_mm(m.lon, m.lat)
            if not (1 <= x <= self.W - 1 and 1 <= y <= self.H - 1):
                continue
            self.result.marker_refs[m.label] = self.result.ref(x, y)
            if m.kind == "place":
                r = 1.55
                out.append(
                    f'<circle cx="{_f(x)}" cy="{_f(y)}" r="{r + 0.3}" fill="#fff"/>'
                    f'<circle cx="{_f(x)}" cy="{_f(y)}" r="{r}" fill="{self.s["accent"]}"/>'
                    f'<text x="{_f(x)}" y="{_f(y + 0.62)}" font-size="1.75" font-weight="700" '
                    f'fill="#fff" text-anchor="middle">{m.number}</text>'
                )
                self.placer.take(Point(x, y).buffer(r + 0.4))
                self._point_label(m.label, x, y, r + 0.75, 1.9, weight=650)
                continue
            r = 2.3
            icon = {"home": "house", "stay": "bed-double", "work": "briefcase"}[m.kind]
            out.append(
                f'<circle cx="{_f(x)}" cy="{_f(y)}" r="{r + 0.45}" fill="#fff"/>'
                f'<circle cx="{_f(x)}" cy="{_f(y)}" r="{r}" fill="{self.s["home"]}"/>'
                + self._icon(icon, x, y, 2.6, "#fff")
            )
            self.placer.take(Point(x, y).buffer(r + 0.5))
            self._point_label(m.label.upper(), x, y, r + 0.85, 2.1, weight=750, spacing=0.18)
        return "".join(out)

    def _pois(self) -> str:
        if not self.show_pois:
            return ""
        fx, fy = self.focus if self.focus else (self.W / 2, self.H / 2)
        counts: dict[str, int] = {}
        out = []
        r = 1.25 if self.detail else 1.35
        candidates = sorted(
            (p for p in self.d.pois if p.kind in POI_STYLE),
            key=lambda p: (not p.name, math.hypot(p.x - fx, p.y - fy)),
        )
        # Stations and sights first so they win space.
        candidates.sort(key=lambda p: p.kind not in {"station", "museum", "attraction"})
        seen_names: set[tuple[str, str]] = set()
        for poi in candidates:
            icon, color, cap, labelled = POI_STYLE[poi.kind]
            if counts.get(poi.kind, 0) >= cap:
                continue
            if not (3 <= poi.x <= self.W - 3 and 3 <= poi.y <= self.H - 3):
                continue
            if poi.name and (poi.kind, poi.name) in seen_names:
                continue
            disc = Point(poi.x, poi.y).buffer(r + 0.35)
            if not self.placer.try_take(disc):
                continue
            counts[poi.kind] = counts.get(poi.kind, 0) + 1
            if poi.name:
                seen_names.add((poi.kind, poi.name))
            fill = color if self.mode == "color" else "#1a1a1a"
            out.append(
                f'<circle cx="{_f(poi.x)}" cy="{_f(poi.y)}" r="{_f(r + 0.3)}" fill="#fff"/>'
                f'<circle cx="{_f(poi.x)}" cy="{_f(poi.y)}" r="{_f(r)}" fill="{fill}"/>'
                + self._icon(icon, poi.x, poi.y, r * 1.35, "#fff")
            )
            distance = self.frame.ground_metres(math.hypot(poi.x - fx, poi.y - fy))
            self.result.pois.append(
                PlacedPoi(poi.kind, poi.name, self.result.ref(poi.x, poi.y), distance)
            )
            if labelled and poi.name:
                self._point_label(poi.name, poi.x, poi.y, r + 0.7, 1.75, weight=600)
        return "".join(out)

    # -- labels -------------------------------------------------------

    def _point_label(
        self,
        text: str,
        x: float,
        y: float,
        offset: float,
        size: float,
        *,
        weight: int = 500,
        italic: bool = False,
        spacing: float = 0.0,
        color: str | None = None,
    ) -> bool:
        w = text_width(text, size, spacing)
        h = size * 0.95
        options = [
            (x + offset, y - h / 2, "start"),
            (x - offset - w, y - h / 2, "end"),
            (x - w / 2, y - offset - h, "middle"),
            (x - w / 2, y + offset, "middle"),
        ]
        for left, top, anchor in options:
            rect = box(left, top - 0.05, left + w, top + h + 0.05)
            if self.placer.try_take(rect):
                tx = {"start": left, "end": left + w, "middle": left + w / 2}[anchor]
                self.labels.append(
                    f'<text x="{_f(tx)}" y="{_f(top + h * 0.78)}" font-size="{size}" '
                    f'font-weight="{weight}" text-anchor="{anchor}" '
                    f"{'font-style="italic" ' if italic else ''}"
                    f'letter-spacing="{spacing}" fill="{color or self.s["text"]}" '
                    f'stroke="{self.s["halo"]}" stroke-width="{_f(size * 0.3)}" '
                    f'paint-order="stroke" stroke-linejoin="round">{_esc(text)}</text>'
                )
                return True
        return False

    def _line_labels(
        self, items: list[tuple[str, int, LineString]], *, size_for: dict[int, float], style: str
    ) -> None:
        """Place labels along lines; items are (name, rank, merged line)."""
        items.sort(key=lambda t: (-t[1], -t[2].length))
        spots: dict[str, list[Point]] = {}
        for name, rank, line in items:
            size = size_for.get(rank, size_for[min(size_for)])
            length = text_width(name, size) + 1.2
            if line.length < length * 1.15:
                continue
            copies = max(1, int(line.length // 95))
            placed = 0
            for i in range(copies):
                centre = line.length * (i + 0.5) / copies
                for shift in (0, 0.18, -0.18, 0.33, -0.33):
                    c = centre + shift * line.length / copies
                    s0, s1 = c - length / 2, c + length / 2
                    if s0 < 0 or s1 > line.length:
                        continue
                    seg = ops.substring(line, s0, s1)
                    if not isinstance(seg, LineString) or seg.length < length * 0.9:
                        continue
                    seg = seg.simplify(0.25)
                    total, biggest = _turning(seg)
                    if total > 50 or biggest > 32:
                        continue
                    mid = seg.interpolate(0.5, normalized=True)
                    if any(mid.distance(o) < 45 for o in spots.get(name, [])):
                        continue
                    shape = seg.buffer(size * 0.62, cap_style="flat")
                    if not self.placer.try_take(shape):
                        continue
                    spots.setdefault(name, []).append(mid)
                    coords = list(seg.coords)
                    if coords[-1][0] < coords[0][0]:
                        coords.reverse()
                    self._label_id += 1
                    pid = f"{self.p}-l{self._label_id}"
                    self.defs.append(f'<path id="{pid}" d="{_path(coords)}"/>')
                    if style == "water":
                        attrs = (
                            f'font-style="italic" font-weight="500" fill="{self.s["water_text"]}"'
                        )
                    else:
                        attrs = f'font-weight="{560 if rank >= 3 else 480}" fill="{self.s["text"]}"'
                    self.labels.append(
                        f'<text font-size="{size}" {attrs} stroke="{self.s["halo"]}" '
                        f'stroke-width="{_f(size * 0.32)}" paint-order="stroke" '
                        f'stroke-linejoin="round" dy="{_f(size * 0.34)}">'
                        f'<textPath href="#{pid}" startOffset="50%" text-anchor="middle">'
                        f"{_esc(name)}</textPath></text>"
                    )
                    placed += 1
                    break
            if placed == 0:
                continue

    def _street_labels(self) -> None:
        by_name: dict[str, tuple[int, list[LineString]]] = {}
        for road in self.d.roads:
            group = ROAD_GROUP.get(road.kind, "path")
            if not road.name or road.tunnel:
                continue
            rank = LABEL_RANK[group]
            if rank == 0 and not self.detail:
                continue
            if not self.detail and rank < 1:
                continue
            best, lines = by_name.get(road.name, (0, []))
            lines.append(LineString(road.coords))
            by_name[road.name] = (max(best, rank), lines)
        inner = box(1.5, 1.5, self.W - 1.5, self.H - 1.5)
        items = []
        for name, (rank, lines) in by_name.items():
            merged = ops.linemerge(MultiLineString(lines))
            for part in _lines(merged.intersection(inner)):
                items.append((name, rank, part))
        sizes = (
            {0: 1.55, 1: 1.7, 2: 1.8, 3: 1.95, 4: 2.05, 5: 2.1}
            if self.detail
            else {1: 1.5, 2: 1.6, 3: 1.75, 4: 1.85, 5: 1.9}
        )
        self._line_labels(items, size_for=sizes, style="street")

    def _water_labels(self) -> None:
        by_name: dict[str, list[LineString]] = {}
        for ww in self.d.waterways:
            if ww.name and ww.kind in {"river", "canal"}:
                by_name.setdefault(ww.name, []).append(LineString(ww.coords))
        inner = box(1.5, 1.5, self.W - 1.5, self.H - 1.5)
        items = []
        for name, lines in by_name.items():
            merged = ops.linemerge(MultiLineString(lines))
            for part in _lines(merged.intersection(inner)):
                items.append((name, 3, part))
        self._line_labels(items, size_for={3: 1.85}, style="water")
        for area in self.d.water:
            if area.name and area.area > 900:
                poly = Polygon(area.rings[0]).buffer(0)
                pt = poly.representative_point()
                if 0 < pt.x < self.W and 0 < pt.y < self.H:
                    self._point_label(
                        area.name, pt.x, pt.y, 0, 2.0, italic=True, color=self.s["water_text"]
                    )

    def _place_labels(self) -> None:
        order = {"suburb": 0, "quarter": 1, "neighbourhood": 2}
        size = {"suburb": 2.5, "quarter": 2.2, "neighbourhood": 2.0}
        if self.detail:
            size = {"suburb": 2.7, "quarter": 2.4, "neighbourhood": 2.2}
        for place in sorted(self.d.places, key=lambda p: order.get(p.kind, 9)):
            if not place.name or place.kind not in order:
                continue
            if not self.detail and place.kind == "neighbourhood" and len(place.name) > 22:
                continue
            text = place.name.upper()
            fs = size[place.kind]
            w = text_width(text, fs, 0.28)
            rect = box(place.x - w / 2, place.y - fs / 2, place.x + w / 2, place.y + fs / 2)
            if self.placer.try_take(rect):
                self.labels.append(
                    f'<text x="{_f(place.x)}" y="{_f(place.y + fs * 0.36)}" font-size="{fs}" '
                    f'font-weight="650" letter-spacing=".28" text-anchor="middle" '
                    f'fill="{self.s["place_text"]}" fill-opacity=".85" stroke="{self.s["halo"]}" '
                    f'stroke-width="{_f(fs * 0.28)}" paint-order="stroke" '
                    f'stroke-linejoin="round">{_esc(text)}</text>'
                )

    def _park_labels(self) -> None:
        parks = sorted(
            (a for a in self.d.green if a.name and a.kind in {"park", "forest", "cemetery"}),
            key=lambda a: -a.area,
        )
        for area in parks:
            name = area.name
            if not name or area.area < (140 if self.detail else 260):
                continue
            poly = Polygon(area.rings[0]).buffer(0)
            pt = poly.representative_point()
            if not (0 < pt.x < self.W and 0 < pt.y < self.H):
                continue
            size = 1.8 if self.detail else 1.7
            w = text_width(name, size)
            minx, _, maxx, _ = poly.bounds
            if w > (maxx - minx) * 1.3:
                continue
            self._point_label(
                name, pt.x, pt.y, 0, size, italic=True, weight=520, color=self.s["green_text"]
            )

    # -- furniture ----------------------------------------------------

    def _grid(self) -> str:
        cw, ch = self.W / self.cols, self.H / self.rows
        lines = []
        for i in range(1, self.cols):
            lines.append(f"M{_f(i * cw)} 0V{_f(self.H)}")
        for j in range(1, self.rows):
            lines.append(f"M0 {_f(j * ch)}H{_f(self.W)}")
        out = [
            f'<path d="{"".join(lines)}" stroke="{self.s["grid"]}" stroke-opacity=".22" '
            'stroke-width=".12" stroke-dasharray=".5 .7" fill="none"/>'
        ]
        tab = 2.6
        for i in range(self.cols):
            x = (i + 0.5) * cw
            out.append(
                f'<rect x="{_f(x - tab / 2)}" y="0" width="{tab}" height="{tab}" rx=".5" '
                f'fill="#fff" fill-opacity=".92"/>'
                f'<text x="{_f(x)}" y="{_f(tab * 0.72)}" font-size="1.7" font-weight="700" '
                f'text-anchor="middle" fill="{self.s["grid"]}">{chr(65 + i)}</text>'
            )
            self.placer.take(box(x - tab / 2, 0, x + tab / 2, tab))
        for j in range(self.rows):
            y = (j + 0.5) * ch
            out.append(
                f'<rect x="0" y="{_f(y - tab / 2)}" width="{tab}" height="{tab}" rx=".5" '
                f'fill="#fff" fill-opacity=".92"/>'
                f'<text x="{_f(tab / 2)}" y="{_f(y + 0.6)}" font-size="1.7" font-weight="700" '
                f'text-anchor="middle" fill="{self.s["grid"]}">{j + 1}</text>'
            )
            self.placer.take(box(0, y - tab / 2, tab, y + tab / 2))
        return "".join(out)

    def _furniture(self) -> str:
        out = []
        # Title card, top left (after the first grid column tab).
        title = self.title.upper()
        sub = self.subtitle or f"1 : {self.frame.scale:,}".replace(",", " ")
        badge = 5.2 if self.number else 0.0
        tw = max(text_width(title, 2.5, 0.25), text_width(sub, 1.6)) + 4 + badge
        x0, y0 = 4.0, 4.0
        tx = x0 + 2 + badge
        out.append(
            f'<rect x="{x0}" y="{y0}" width="{_f(tw)}" height="6.4" rx="1" fill="#fff" '
            f'stroke="{self.s["grid"]}" stroke-width=".18"/>'
            f'<text x="{_f(tx)}" y="{y0 + 3.0}" font-size="2.5" font-weight="760" '
            f'letter-spacing=".25" fill="{self.s["text"]}">{_esc(title)}</text>'
            f'<text x="{_f(tx)}" y="{y0 + 5.3}" font-size="1.6" '
            f'fill="{self.s["text"]}" fill-opacity=".75">{_esc(sub)}</text>'
        )
        if self.number:
            out.append(
                f'<circle cx="{x0 + 3.4}" cy="{y0 + 3.2}" r="2.1" fill="{self.s["grid"]}"/>'
                f'<text x="{x0 + 3.4}" y="{y0 + 4.05}" font-size="2.4" font-weight="800" '
                f'text-anchor="middle" fill="#fff">{self.number}</text>'
            )
        self.placer.take(box(x0 - 0.5, y0 - 0.5, x0 + tw + 0.5, y0 + 6.9))
        # North arrow next to the title card.
        nx, ny = x0 + tw + 3.2, y0 + 3.2
        out.append(
            f'<g transform="translate({_f(nx)} {_f(ny)})">'
            f'<circle r="2.4" fill="#fff" stroke="{self.s["grid"]}" stroke-width=".18"/>'
            f'<path d="M0 -1.7 L1 .9 L0 .35 L-1 .9Z" fill="{self.s["grid"]}"/>'
            f'<text y="-2.9" font-size="1.4" font-weight="700" text-anchor="middle" '
            f'fill="{self.s["grid"]}">N</text></g>'
        )
        self.placer.take(box(nx - 2.6, ny - 4.4, nx + 2.6, ny + 2.6))
        # Scale bar, bottom left.
        metres = _nice_distance(self.frame.ground_metres(22))
        length = metres * 1000 / self.frame.scale
        sx, sy = 4.0, self.H - 4.2
        half = length / 2
        label = f"{metres} m" if metres < 1000 else f"{metres / 1000:g} km"
        out.append(
            f'<rect x="{_f(sx - 1)}" y="{_f(sy - 3.2)}" width="{_f(length + 2 + 8)}" height="5" '
            f'rx=".8" fill="#fff" fill-opacity=".92"/>'
            f'<rect x="{_f(sx)}" y="{_f(sy)}" width="{_f(half)}" height=".8" '
            f'fill="{self.s["grid"]}"/>'
            f'<rect x="{_f(sx + half)}" y="{_f(sy)}" width="{_f(half)}" height=".8" fill="#fff" '
            f'stroke="{self.s["grid"]}" stroke-width=".15"/>'
            f'<text x="{_f(sx)}" y="{_f(sy - 0.8)}" font-size="1.5" '
            f'fill="{self.s["text"]}">0</text>'
            f'<text x="{_f(sx + length + 1)}" y="{_f(sy + 0.9)}" font-size="1.6" font-weight="600" '
            f'fill="{self.s["text"]}">{label}</text>'
        )
        self.placer.take(box(sx - 1, sy - 3.2, sx + length + 9, sy + 1.8))
        # Attribution, bottom right (required by the ODbL).
        attribution = "© OpenStreetMap contributors"
        aw = text_width(attribution, 1.45) + 2
        out.append(
            f'<rect x="{_f(self.W - aw - 1.2)}" y="{_f(self.H - 3.6)}" width="{_f(aw)}" '
            f'height="2.6" rx=".6" fill="#fff" fill-opacity=".9"/>'
            f'<text x="{_f(self.W - 2.2)}" y="{_f(self.H - 1.75)}" font-size="1.45" '
            f'text-anchor="end" fill="{self.s["text"]}" fill-opacity=".8">{attribution}</text>'
        )
        self.placer.take(box(self.W - aw - 1.2, self.H - 3.6, self.W, self.H))
        return "".join(out)

    # -- assembly -----------------------------------------------------

    def render(self) -> MapResult:
        self.defs: list[str] = []
        self.labels: list[str] = []
        self._label_id = 0
        self._clip_id = 0
        p = self.p
        self.defs.append(
            f'<clipPath id="{p}-clip"><rect width="{_f(self.W)}" height="{_f(self.H)}" rx="1.2"/>'
            "</clipPath>"
        )
        greens = [a for a in self.d.green if a.kind in self.s]
        greens.sort(key=lambda a: -a.area)
        base = [
            f'<rect width="{_f(self.W)}" height="{_f(self.H)}" fill="{self.s["land"]}"/>',
            self._areas(greens),
            self._sea(),
            self._areas(self.d.water, "water"),
            self._waterways(),
            self._buildings(),
            self._roads(),
            self._rails(),
        ]
        furniture = self._grid() + self._furniture()
        symbols = self._markers() + self._pois()
        self._place_labels()
        self._water_labels()
        self._street_labels()
        self._park_labels()
        svg = (
            f'<svg class="map" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(self.W)} '
            f'{_f(self.H)}" width="{_f(self.W)}mm" height="{_f(self.H)}mm">'
            f"<defs>{''.join(self.defs)}</defs>"
            f'<g clip-path="url(#{p}-clip)">{"".join(base)}'
            f"{''.join(self.labels)}{symbols}{furniture}</g>"
            f'<rect x=".1" y=".1" width="{_f(self.W - 0.2)}" height="{_f(self.H - 0.2)}" rx="1.2" '
            f'fill="none" stroke="{self.s["grid"]}" stroke-width=".25"/></svg>'
        )
        self.result.svg = svg
        return self.result
