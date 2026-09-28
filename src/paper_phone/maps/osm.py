"""Fetch OpenStreetMap data for a map frame from Overpass and project it to millimetres."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from paper_phone.http import Http

OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
R = 6378137.0

Pt = tuple[float, float]
Ring = list[Pt]


def merc(lon: float, lat: float) -> Pt:
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def unmerc(x: float, y: float) -> Pt:
    return math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)


@dataclass(frozen=True)
class Frame:
    """A north-up map window: centre, scale (1:scale) and size on paper in mm."""

    lat: float
    lon: float
    scale: int
    width: float
    height: float

    @property
    def k(self) -> float:
        """Millimetres on paper per Web-Mercator metre."""
        return 1000 / self.scale * math.cos(math.radians(self.lat))

    def to_mm(self, lon: float, lat: float) -> Pt:
        cx, cy = merc(self.lon, self.lat)
        x, y = merc(lon, lat)
        return (x - cx) * self.k + self.width / 2, (cy - y) * self.k + self.height / 2

    def to_lonlat(self, x_mm: float, y_mm: float) -> Pt:
        cx, cy = merc(self.lon, self.lat)
        return unmerc(cx + (x_mm - self.width / 2) / self.k, cy - (y_mm - self.height / 2) / self.k)

    def bbox(self, pad: float = 0.08) -> tuple[float, float, float, float]:
        """(south, west, north, east) with a little padding for labels and clipping."""
        west, north = self.to_lonlat(-self.width * pad, -self.height * pad)
        east, south = self.to_lonlat(self.width * (1 + pad), self.height * (1 + pad))
        return south, west, north, east

    def ground_metres(self, mm: float) -> float:
        return mm * self.scale / 1000


DETAIL_ROADS = "service|footway|cycleway|path|steps|track|bridleway"
MAIN_ROADS = (
    "motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|primary_link|"
    "secondary_link|tertiary_link|unclassified|residential|living_street|pedestrian"
)
POI_AMENITY = (
    "cafe|restaurant|bar|pub|pharmacy|atm|bank|hospital|police|post_office|library|"
    "toilets|drinking_water|bicycle_rental|marketplace|ice_cream"
)


def build_query(frame: Frame, detail: bool) -> str:
    s, w, n, e = frame.bbox()
    coarse = frame.scale > 20000
    roads = MAIN_ROADS + ("|" + DETAIL_ROADS if detail else "")
    if coarse:
        roads = "motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|primary_link"
    buildings = "" if coarse else "\n  way[building];\n  relation[building];"
    pois = (
        f"""
  node[amenity~"^({POI_AMENITY})$"];
  node[shop~"^(supermarket|bakery|convenience)$"];
  way[shop=supermarket];
  node[tourism~"^(museum|attraction|viewpoint)$"];
  way[tourism~"^(museum|attraction)$"];
  node[railway=tram_stop];"""
        if detail
        else """
  node[tourism~"^(museum|attraction)$"][name];
  way[tourism~"^(museum|attraction)$"][name];
  node[amenity=hospital][name];"""
    )
    return f"""[out:json][timeout:180][bbox:{s:.6f},{w:.6f},{n:.6f},{e:.6f}];
(
  way[highway~"^({roads})$"];
  way[railway~"^(rail|tram|light_rail|narrow_gauge)$"];
  way[waterway~"^(river|canal|stream|riverbank)$"];
  way[natural~"^(water|wood|scrub|beach|sand|heath|coastline)$"];
  relation[natural~"^(water|wood|beach)$"];
  relation[waterway=riverbank];
  way[leisure~"^(park|garden|playground|pitch|nature_reserve|golf_course)$"];
  relation[leisure~"^(park|garden|nature_reserve)$"];
  way[landuse~"^(grass|forest|cemetery|recreation_ground|meadow|allotments|village_green)$"];
  relation[landuse~"^(forest|cemetery|grass|recreation_ground)$"];
  way[amenity=grave_yard];{buildings}
  node[place~"^(suburb|neighbourhood|quarter)$"];
  node[railway~"^(station|halt)$"];{pois}
);
out geom;"""


@dataclass
class Line:
    kind: str
    coords: list[Pt]
    name: str | None = None
    bridge: bool = False
    tunnel: bool = False
    service: bool = False


@dataclass
class Area:
    kind: str
    rings: list[Ring]
    name: str | None = None

    @property
    def area(self) -> float:
        return sum(abs(_shoelace(r)) for r in self.rings)


@dataclass
class Point:
    kind: str
    x: float
    y: float
    name: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class MapData:
    roads: list[Line] = field(default_factory=list)
    rails: list[Line] = field(default_factory=list)
    waterways: list[Line] = field(default_factory=list)
    coastline: list[Line] = field(default_factory=list)
    water: list[Area] = field(default_factory=list)
    green: list[Area] = field(default_factory=list)
    buildings: list[Ring] = field(default_factory=list)
    places: list[Point] = field(default_factory=list)
    pois: list[Point] = field(default_factory=list)


def _shoelace(ring: Ring) -> float:
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in itertools.pairwise(ring))


def _assemble(segments: list[list[Pt]]) -> list[Ring]:
    """Join way segments that share endpoints into closed rings."""
    rings: list[Ring] = []
    open_parts = []
    for seg in segments:
        if len(seg) >= 4 and seg[0] == seg[-1]:
            rings.append(seg)
        elif len(seg) >= 2:
            open_parts.append(list(seg))
    while open_parts:
        current = open_parts.pop()
        changed = True
        while changed and current[0] != current[-1]:
            changed = False
            for i, part in enumerate(open_parts):
                if part[0] == current[-1]:
                    current += part[1:]
                elif part[-1] == current[-1]:
                    current += part[::-1][1:]
                elif part[-1] == current[0]:
                    current = part + current[1:]
                elif part[0] == current[0]:
                    current = part[::-1] + current[1:]
                else:
                    continue
                open_parts.pop(i)
                changed = True
                break
        if current[0] == current[-1] and len(current) >= 4:
            rings.append(current)
    return rings


def _green_kind(tags: dict[str, str]) -> str | None:
    leisure, landuse, natural = tags.get("leisure"), tags.get("landuse"), tags.get("natural")
    if leisure in {"park", "garden", "nature_reserve", "golf_course"} or landuse in {
        "recreation_ground",
        "village_green",
    }:
        return "park"
    if leisure in {"playground", "pitch"}:
        return "pitch"
    if landuse == "forest" or natural in {"wood", "scrub", "heath"}:
        return "forest"
    if landuse in {"grass", "meadow", "allotments"}:
        return "grass"
    if landuse == "cemetery" or tags.get("amenity") == "grave_yard":
        return "cemetery"
    if natural in {"beach", "sand"}:
        return "beach"
    return None


def poi_kind(tags: dict[str, str]) -> str | None:
    if tags.get("railway") in {"station", "halt"} or tags.get("public_transport") == "station":
        return "station"
    if tags.get("railway") == "tram_stop":
        return "tram"
    amenity, shop, tourism = tags.get("amenity"), tags.get("shop"), tags.get("tourism")
    mapping = {
        "cafe": "cafe",
        "ice_cream": "cafe",
        "restaurant": "restaurant",
        "bar": "bar",
        "pub": "bar",
        "pharmacy": "pharmacy",
        "atm": "atm",
        "bank": "atm",
        "hospital": "hospital",
        "police": "police",
        "post_office": "post",
        "library": "library",
        "toilets": "toilets",
        "drinking_water": "water",
        "bicycle_rental": "bike",
        "marketplace": "market",
    }
    if amenity in mapping:
        return mapping[amenity]
    if shop in {"supermarket", "convenience"}:
        return "supermarket"
    if shop == "bakery":
        return "bakery"
    if tourism in {"museum", "attraction", "viewpoint"}:
        return tourism
    return None


def fetch(http: Http, frame: Frame, detail: bool) -> MapData:
    raw = http.post_json(OVERPASS, {"data": build_query(frame, detail)}, ttl=30 * 24 * 3600)
    return parse(raw, frame)


def parse(raw: dict, frame: Frame) -> MapData:
    data = MapData()
    project = frame.to_mm

    def coords(geometry: list[dict]) -> list[Pt]:
        return [project(g["lon"], g["lat"]) for g in geometry if g]

    for el in raw.get("elements", []):
        tags: dict[str, str] = el.get("tags", {})
        kind = el["type"]
        if kind == "node":
            x, y = project(el["lon"], el["lat"])
            if "place" in tags and tags.get("name"):
                data.places.append(Point(tags["place"], x, y, tags["name"], tags))
            elif (pk := poi_kind(tags)) is not None:
                data.pois.append(Point(pk, x, y, tags.get("name"), tags))
            continue

        if kind == "way":
            geom = coords(el.get("geometry", []))
            if len(geom) < 2:
                continue
            closed = geom[0] == geom[-1] and len(geom) >= 4
            if "highway" in tags:
                if tags.get("area") == "yes":
                    continue
                data.roads.append(
                    Line(
                        tags["highway"],
                        geom,
                        tags.get("name"),
                        bridge=tags.get("bridge") not in (None, "no"),
                        tunnel=tags.get("tunnel") not in (None, "no")
                        or tags.get("layer", "0").startswith("-"),
                    )
                )
            elif "railway" in tags:
                data.rails.append(
                    Line(
                        tags["railway"],
                        geom,
                        tags.get("name"),
                        tunnel=tags.get("tunnel") not in (None, "no"),
                        service="service" in tags or tags.get("usage") in {"industrial"},
                    )
                )
            elif tags.get("natural") == "coastline":
                data.coastline.append(Line("coastline", geom))
            elif tags.get("waterway") in {"river", "canal", "stream"}:
                data.waterways.append(
                    Line(
                        tags["waterway"],
                        geom,
                        tags.get("name"),
                        tunnel=tags.get("tunnel") not in (None, "no"),
                    )
                )
            elif closed and (tags.get("natural") == "water" or tags.get("waterway") == "riverbank"):
                data.water.append(Area("water", [geom], tags.get("name")))
            elif closed and "building" in tags:
                data.buildings.append(geom)
            elif closed and (gk := _green_kind(tags)):
                data.green.append(Area(gk, [geom], tags.get("name")))
            elif (pk := poi_kind(tags)) is not None:
                xs, ys = zip(*geom, strict=True)
                data.pois.append(
                    Point(pk, sum(xs) / len(xs), sum(ys) / len(ys), tags.get("name"), tags)
                )
            continue

        if kind == "relation":
            segments = [
                coords(m["geometry"])
                for m in el.get("members", [])
                if m.get("type") == "way" and m.get("geometry")
            ]
            rings = _assemble(segments)
            if not rings:
                continue
            if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
                data.water.append(Area("water", rings, tags.get("name")))
            elif "building" in tags:
                data.buildings.extend(rings)
            elif gk := _green_kind(tags):
                data.green.append(Area(gk, rings, tags.get("name")))
    return data
