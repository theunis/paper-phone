"""User configuration, loaded from a YAML file and validated with pydantic."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Edition = Literal["daily", "weekly", "monthly", "travel"]
EDITIONS: tuple[Edition, ...] = ("daily", "weekly", "monthly", "travel")
Mode = Literal["color", "bw"]
Paper = Literal["a4", "letter"]
BackLayout = Literal["maps", "poster", "blank"]

# A page is one module name, or two half-page module names stacked.
PageSpec = str | list[str]


class Settings(BaseSettings):
    """Process-level settings from the environment (PAPER_PHONE_*)."""

    model_config = SettingsConfigDict(env_prefix="PAPER_PHONE_", env_file=".env", extra="ignore")

    cache_dir: Path = Field(default=Path.home() / ".cache" / "paper-phone")
    output_dir: Path = Path("output")
    browser_channel: str = "chrome"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Place(_Model):
    """Something to geocode: a free-text query, or explicit coordinates."""

    name: str | None = None
    query: str | None = None
    lat: float | None = None
    lon: float | None = None
    note: str | None = None

    @property
    def label(self) -> str:
        return self.name or (self.query or "").split(",")[0] or "Here"


class Contact(_Model):
    name: str
    phone: str | None = None
    note: str | None = None


class Owner(_Model):
    name: str | None = None
    phone: str | None = None
    email: str | None = None


class LanguageConfig(_Model):
    learn: str = "es"
    native: Literal["en", "nl"] = "en"


class Session(_Model):
    """One training session. A plain string in YAML becomes the title."""

    title: str
    type: Literal["run", "bike", "swim", "strength", "yoga", "walk", "cross", "rest", "race"] = (
        "run"
    )
    distance_km: float | None = None
    duration_min: int | None = None
    intensity: Literal["easy", "moderate", "hard", "race"] | None = None
    detail: str | None = None


DayKey = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_KEYS: tuple[DayKey, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _coerce_week(value: object) -> object:
    if isinstance(value, dict):
        out = {}
        for key, session in value.items():
            if isinstance(session, str):
                lowered = session.lower()
                kind = "rest" if lowered in {"rest", "off", "rust"} else "run"
                session = {"title": session[:1].upper() + session[1:], "type": kind}
            out[key] = session
        return out
    return value


class TrainingGoal(_Model):
    name: str
    date: dt.date


class TrainingConfig(_Model):
    name: str = "Training"
    start: dt.date | None = None  # Monday of plan week 1
    goal: TrainingGoal | None = None
    weekly: dict[DayKey, Session] = Field(default_factory=dict)
    plan: list[dict[DayKey, Session]] = Field(default_factory=list)

    _coerce_weekly = field_validator("weekly", mode="before")(_coerce_week)

    @field_validator("plan", mode="before")
    @classmethod
    def _coerce_plan(cls, value: object) -> object:
        if isinstance(value, list):
            return [_coerce_week(week) for week in value]
        return value


class Task(_Model):
    title: str
    due: dt.date | None = None
    priority: bool = False
    tags: list[str] = Field(default_factory=list)
    done: bool = False


class Event(_Model):
    title: str
    date: dt.date
    start: dt.time | None = None
    end: dt.time | None = None
    location: str | None = None


class MapSpec(_Model):
    """A map on the back of the sheet."""

    title: str
    place: str | Place  # "home", "work", "stay", "city", "fit" (all your places), or a Place
    scale: int = 7500  # 1:scale; for "fit" the most zoomed-in scale allowed


class TransportLeg(_Model):
    date: dt.date
    time: str | None = None
    title: str
    detail: str | None = None


class TripConfig(_Model):
    destination: str
    start: dt.date
    end: dt.date
    stay: Place | None = None
    language: str | None = None  # phrasebook, default from country
    currency: str | None = None  # default from country
    transport: list[TransportLeg] = Field(default_factory=list)
    itinerary: dict[dt.date, list[str]] = Field(default_factory=dict)
    places: list[Place] = Field(default_factory=list)
    packing: list[str] = Field(default_factory=list)
    include_calendars: bool = False  # show your normal calendars during the trip


class RecipeConfig(_Model):
    diet: Literal["any", "vegetarian", "vegan", "pescatarian"] = "any"
    pick: str | None = None  # recipe id to force
    extra_file: Path | None = None


class Config(_Model):
    owner: Owner = Field(default_factory=Owner)
    home: Place = Field(default_factory=lambda: Place(query="Utrecht, Netherlands"))
    work: Place | None = None
    city: Place | None = None  # city-centre map; defaults to the home town
    country: str = "NL"  # public holidays
    paper: Paper = "a4"
    language: LanguageConfig = Field(default_factory=LanguageConfig)
    training: TrainingConfig | None = None
    tasks: list[Task] = Field(default_factory=list)
    tasks_file: Path | None = None
    calendars: list[str] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    habits: list[str] = Field(
        default_factory=lambda: ["Phone-free morning", "Move 30 min", "Read", "Water ×8"]
    )
    contacts: list[Contact] = Field(default_factory=list)
    recipes: RecipeConfig = Field(default_factory=RecipeConfig)
    trip: TripConfig | None = None
    back: BackLayout = "maps"
    maps: list[MapSpec] | None = None
    pages: dict[Edition, list[PageSpec]] = Field(default_factory=dict)
    contact_email: str | None = None  # sent to Nominatim/Overpass per their usage policy

    base_dir: Path = Path(".")

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else self.base_dir / path


def load_config(path: Path | None) -> Config:
    """Load a config file; without one, return the defaults."""
    if path is None:
        return Config()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["base_dir"] = path.parent
    return Config.model_validate(data)


def get_settings() -> Settings:
    return Settings()
