"""Geocoding with OpenStreetMap Nominatim (max 1 request/second, cached for good)."""

from __future__ import annotations

from dataclasses import dataclass

from paper_phone.config import Place
from paper_phone.http import Http

NOMINATIM = "https://nominatim.openstreetmap.org"
FOREVER = 10 * 365 * 24 * 3600


@dataclass(frozen=True)
class Geo:
    name: str
    lat: float
    lon: float
    country_code: str  # ISO alpha-2, upper case
    city: str | None
    suburb: str | None
    display: str
    road: str | None = None
    house_number: str | None = None

    @property
    def short_address(self) -> str:
        parts = [p for p in (self.road, self.house_number) if p]
        street = " ".join(parts)
        return ", ".join(p for p in (street, self.city) if p) or self.display


def _from_result(result: dict, name: str | None) -> Geo:
    address = result.get("address", {})
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
    )
    suburb = address.get("suburb") or address.get("neighbourhood") or address.get("quarter")
    return Geo(
        name=name or result.get("name") or city or result["display_name"].split(",")[0],
        lat=float(result["lat"]),
        lon=float(result["lon"]),
        country_code=address.get("country_code", "").upper(),
        city=city,
        suburb=suburb,
        display=result["display_name"],
        road=address.get("road") or address.get("pedestrian"),
        house_number=address.get("house_number"),
    )


def geocode(http: Http, place: Place) -> Geo:
    if place.lat is not None and place.lon is not None:
        result = http.get_json(
            f"{NOMINATIM}/reverse",
            {
                "lat": place.lat,
                "lon": place.lon,
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 18,
            },
            ttl=FOREVER,
            min_interval=1.1,
        )
        result["lat"], result["lon"] = place.lat, place.lon
        return _from_result(result, place.name)
    if not place.query:
        raise ValueError(f"Place {place!r} needs a query or lat/lon")
    results = http.get_json(
        f"{NOMINATIM}/search",
        {"q": place.query, "format": "jsonv2", "addressdetails": 1, "limit": 1},
        ttl=FOREVER,
        min_interval=1.1,
    )
    if not results:
        raise ValueError(f"Could not find {place.query!r} on OpenStreetMap")
    return _from_result(results[0], place.name)
