"""Map rendering from a tiny hand-made Overpass response (no network)."""

from __future__ import annotations

import pytest

from paper_phone.config import Mode
from paper_phone.maps.osm import Frame, parse
from paper_phone.maps.render import MapRenderer, Marker

LAT, LON = 52.09, 5.12


def _way(tags: dict, pts: list[tuple[float, float]]) -> dict:
    return {"type": "way", "tags": tags, "geometry": [{"lat": a, "lon": b} for a, b in pts]}


def _square(lat: float, lon: float, d: float) -> list[tuple[float, float]]:
    return [(lat, lon), (lat + d, lon), (lat + d, lon + d), (lat, lon + d), (lat, lon)]


RAW = {
    "elements": [
        _way(
            {"highway": "primary", "name": "Maliebaan"},
            [(LAT - 0.004, LON - 0.008), (LAT + 0.004, LON + 0.008)],
        ),
        _way(
            {"highway": "residential", "name": "Oudwijk"}, [(LAT, LON - 0.008), (LAT, LON + 0.008)]
        ),
        _way({"railway": "rail"}, [(LAT - 0.004, LON), (LAT + 0.004, LON)]),
        _way(
            {"railway": "rail", "service": "yard"}, [(LAT - 0.004, LON + 1e-4), (LAT + 0.004, LON)]
        ),
        _way({"natural": "water", "name": "Vijver"}, _square(LAT + 0.001, LON + 0.001, 0.002)),
        _way(
            {"leisure": "park", "name": "Wilhelminapark"}, _square(LAT - 0.003, LON - 0.006, 0.003)
        ),
        _way({"building": "yes"}, _square(LAT - 0.001, LON - 0.001, 0.0003)),
        {
            "type": "node",
            "lat": LAT + 0.001,
            "lon": LON - 0.003,
            "tags": {"amenity": "cafe", "name": "Koffie"},
        },
        {
            "type": "node",
            "lat": LAT - 0.002,
            "lon": LON + 0.004,
            "tags": {"railway": "station", "name": "Maliebaan"},
        },
        {
            "type": "node",
            "lat": LAT + 0.003,
            "lon": LON + 0.005,
            "tags": {"place": "neighbourhood", "name": "Oudwijk"},
        },
    ]
}


MODES: list[Mode] = ["color", "bw"]


@pytest.mark.parametrize("mode", MODES)
def test_renders_print_safe_svg(mode: Mode) -> None:
    frame = Frame(LAT, LON, 6500, 100, 90)
    data = parse(RAW, frame)
    assert len(data.roads) == 2 and len(data.rails) == 2 and data.buildings
    result = MapRenderer(
        data,
        frame,
        mode=mode,
        detail=True,
        prefix="t",
        title="Around home",
        markers=[Marker(LAT, LON, "home", "Home")],
        focus=frame.to_mm(LON, LAT),
        number=2,
    ).render()
    svg = result.svg
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "<pattern" not in svg  # Chrome rasterises patterns when printing
    assert "AROUND HOME" in svg and "OpenStreetMap" in svg
    assert "textPath" in svg  # street names follow the streets
    assert {p.kind for p in result.pois} == {"cafe", "station"}
    assert result.marker_refs["Home"] == result.ref(50, 45)
    assert result.locate(LON, LAT) == f"2 · {result.ref(50, 45)}"
    if mode == "bw":
        assert "clip-path" in svg and "stroke-dasharray" in svg  # vector textures


def test_frame_round_trip() -> None:
    frame = Frame(LAT, LON, 10000, 200, 100)
    x, y = frame.to_mm(LON + 0.01, LAT - 0.005)
    lon, lat = frame.to_lonlat(x, y)
    assert abs(lon - (LON + 0.01)) < 1e-9 and abs(lat - (LAT - 0.005)) < 1e-9
    assert frame.to_mm(LON, LAT) == pytest.approx((100, 50))
