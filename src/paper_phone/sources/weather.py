"""Forecasts and climate normals from Open-Meteo (free, no API key)."""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field

from paper_phone.http import Http

FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

# WMO weather interpretation codes -> (short label, icon name)
WMO: dict[int, tuple[str, str]] = {
    0: ("Clear", "sun"),
    1: ("Mostly clear", "sun"),
    2: ("Partly cloudy", "cloud-sun"),
    3: ("Overcast", "cloud"),
    45: ("Fog", "cloud-fog"),
    48: ("Rime fog", "cloud-fog"),
    51: ("Light drizzle", "cloud-drizzle"),
    53: ("Drizzle", "cloud-drizzle"),
    55: ("Heavy drizzle", "cloud-drizzle"),
    56: ("Freezing drizzle", "cloud-drizzle"),
    57: ("Freezing drizzle", "cloud-drizzle"),
    61: ("Light rain", "cloud-rain"),
    63: ("Rain", "cloud-rain"),
    65: ("Heavy rain", "cloud-rain"),
    66: ("Freezing rain", "cloud-rain"),
    67: ("Freezing rain", "cloud-rain"),
    71: ("Light snow", "cloud-snow"),
    73: ("Snow", "cloud-snow"),
    75: ("Heavy snow", "snowflake"),
    77: ("Snow grains", "cloud-snow"),
    80: ("Showers", "cloud-sun-rain"),
    81: ("Showers", "cloud-sun-rain"),
    82: ("Heavy showers", "cloud-rain"),
    85: ("Snow showers", "cloud-snow"),
    86: ("Snow showers", "cloud-snow"),
    95: ("Thunderstorm", "cloud-lightning"),
    96: ("Thunder & hail", "cloud-lightning"),
    99: ("Thunder & hail", "cloud-lightning"),
}

COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def describe(code: int | None) -> tuple[str, str]:
    return WMO.get(code if code is not None else -1, ("—", "cloud"))


def compass(degrees: float | None) -> str:
    if degrees is None:
        return ""
    return COMPASS[round(degrees / 45) % 8]


def beaufort(kmh: float | None) -> int:
    if kmh is None:
        return 0
    limits = [1, 6, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118]
    return next((i for i, limit in enumerate(limits) if kmh < limit), 12)


@dataclass
class Hour:
    time: dt.datetime
    temp: float
    feels: float
    precip: float
    precip_prob: int
    code: int
    wind: float

    @property
    def icon(self) -> str:
        icon = describe(self.code)[1]
        night = self.time.hour < 7 or self.time.hour >= 20
        if night and icon == "sun":
            return "moon"
        if night and icon == "cloud-sun":
            return "cloud-moon"
        return icon


@dataclass
class Day:
    date: dt.date
    code: int
    tmax: float
    tmin: float
    precip: float
    precip_prob: int | None
    sunrise: dt.datetime | None
    sunset: dt.datetime | None
    daylight_s: float | None
    uv: float | None
    wind_max: float | None
    wind_dir: float | None
    hours: list[Hour] = field(default_factory=list)
    typical: bool = False  # climate normals standing in for a forecast

    @property
    def label(self) -> str:
        return "Typical" if self.typical else describe(self.code)[0]

    @property
    def icon(self) -> str:
        return describe(self.code)[1]

    @property
    def wind_compass(self) -> str:
        return compass(self.wind_dir)

    @property
    def beaufort(self) -> int:
        return beaufort(self.wind_max)


@dataclass
class Forecast:
    timezone: str
    utc_offset_s: int
    days: list[Day]

    def day(self, date: dt.date) -> Day | None:
        return next((d for d in self.days if d.date == date), None)

    def between(self, start: dt.date, end: dt.date) -> list[Day]:
        return [d for d in self.days if start <= d.date <= end]


@dataclass
class Normals:
    """Typical weather for a calendar window, averaged over past years."""

    tmax: float
    tmin: float
    precip_mm_per_day: float
    wet_days_pct: float
    sunshine_h: float | None
    years: int


def _dt(value: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value) if value else None


def forecast(http: Http, lat: float, lon: float) -> Forecast:
    data = http.get_json(
        FORECAST,
        {
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "timezone": "auto",
            "forecast_days": 16,
            "past_days": 1,
            "hourly": "temperature_2m,apparent_temperature,precipitation,"
            "precipitation_probability,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,sunrise,sunset,daylight_duration,uv_index_max,"
            "wind_speed_10m_max,wind_direction_10m_dominant",
        },
        ttl=3 * 3600,
    )
    hourly = data["hourly"]
    hours: dict[dt.date, list[Hour]] = {}
    for i, stamp in enumerate(hourly["time"]):
        if hourly["temperature_2m"][i] is None:
            continue
        when = dt.datetime.fromisoformat(stamp)
        hours.setdefault(when.date(), []).append(
            Hour(
                time=when,
                temp=hourly["temperature_2m"][i],
                feels=hourly["apparent_temperature"][i],
                precip=hourly["precipitation"][i] or 0.0,
                precip_prob=hourly["precipitation_probability"][i] or 0,
                code=hourly["weather_code"][i] or 0,
                wind=hourly["wind_speed_10m"][i] or 0.0,
            )
        )
    daily = data["daily"]
    days = []
    for i, stamp in enumerate(daily["time"]):
        if daily["temperature_2m_max"][i] is None:
            continue
        date = dt.date.fromisoformat(stamp)
        days.append(
            Day(
                date=date,
                code=daily["weather_code"][i] or 0,
                tmax=daily["temperature_2m_max"][i],
                tmin=daily["temperature_2m_min"][i],
                precip=daily["precipitation_sum"][i] or 0.0,
                precip_prob=daily["precipitation_probability_max"][i],
                sunrise=_dt(daily["sunrise"][i]),
                sunset=_dt(daily["sunset"][i]),
                daylight_s=daily["daylight_duration"][i],
                uv=daily["uv_index_max"][i],
                wind_max=daily["wind_speed_10m_max"][i],
                wind_dir=daily["wind_direction_10m_dominant"][i],
                hours=hours.get(date, []),
            )
        )
    return Forecast(timezone=data["timezone"], utc_offset_s=data["utc_offset_seconds"], days=days)


def normals(http: Http, lat: float, lon: float, start: dt.date, end: dt.date) -> Normals:
    """Average weather for the start..end calendar window over the last ten years."""
    last_year = dt.date.today().year - 1
    data = http.get_json(
        ARCHIVE,
        {
            "latitude": round(lat, 2),
            "longitude": round(lon, 2),
            "start_date": f"{last_year - 9}-01-01",
            "end_date": f"{last_year}-12-31",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,sunshine_duration",
            "timezone": "auto",
        },
        ttl=90 * 24 * 3600,
    )
    window = set()
    day = start
    while day <= end:
        window.add((day.month, day.day))
        day += dt.timedelta(days=1)
    daily = data["daily"]
    rows = [
        i
        for i, stamp in enumerate(daily["time"])
        if (int(stamp[5:7]), int(stamp[8:10])) in window
        and daily["temperature_2m_max"][i] is not None
    ]
    if not rows:
        raise ValueError("No climate data for this window")
    precip = [daily["precipitation_sum"][i] or 0.0 for i in rows]
    sunshine = [daily["sunshine_duration"][i] for i in rows if daily["sunshine_duration"][i]]
    return Normals(
        tmax=statistics.fmean(daily["temperature_2m_max"][i] for i in rows),
        tmin=statistics.fmean(daily["temperature_2m_min"][i] for i in rows),
        precip_mm_per_day=statistics.fmean(precip),
        wet_days_pct=100 * sum(p >= 1.0 for p in precip) / len(precip),
        sunshine_h=statistics.fmean(sunshine) / 3600 if sunshine else None,
        years=10,
    )
