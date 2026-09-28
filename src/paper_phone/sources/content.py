"""Bundled content (word decks, phrasebooks, recipes, prompts, country facts) and
deterministic "of the day" picks, so the same date always gives the same page."""

from __future__ import annotations

import datetime as dt
import random
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from paper_phone.http import Http

CONTENT = resources.files("paper_phone") / "content"


def _load(*parts: str) -> Any:
    node = CONTENT
    for part in parts:
        node = node / part
    return yaml.safe_load(node.read_text(encoding="utf-8"))


@cache
def word_deck(code: str) -> dict[str, Any]:
    return _load("words", f"{code}.yaml")


@cache
def phrasebook(code: str) -> dict[str, Any] | None:
    try:
        return _load("phrases", f"{code}.yaml")
    except FileNotFoundError:
        return None


def available(kind: str) -> list[str]:
    return sorted(p.name.removesuffix(".yaml") for p in (CONTENT / kind).iterdir())


@cache
def recipes() -> list[dict[str, Any]]:
    return _load("recipes.yaml")


@cache
def prompts() -> dict[str, list[str]]:
    return _load("prompts.yaml")


@cache
def countries() -> dict[str, dict[str, Any]]:
    return _load("countries.yaml")


def shuffled(items: list[Any], seed: str) -> list[Any]:
    out = list(items)
    random.Random(seed).shuffle(out)
    return out


def pick(items: list[Any], seed: str, index: int, count: int = 1) -> list[Any]:
    """`count` consecutive items from a seeded shuffle, starting at `index * count`."""
    if not items:
        return []
    order = shuffled(items, seed)
    start = (index * count) % len(order)
    return [order[(start + i) % len(order)] for i in range(min(count, len(order)))]


def season(date: dt.date, southern: bool = False) -> str:
    month = date.month
    name = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring"}.get(
        month, "summer" if month in (6, 7, 8) else "autumn"
    )
    if southern:
        name = {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}[
            name
        ]
    return name


def choose_recipes(
    date: dt.date, index: int, *, diet: str, forced: str | None, extra: Path | None, count: int = 1
) -> list[dict[str, Any]]:
    pool = list(recipes())
    if extra and extra.exists():
        pool += yaml.safe_load(extra.read_text(encoding="utf-8")) or []
    if forced:
        chosen = [r for r in pool if r["id"] == forced]
        if chosen:
            return chosen
    allowed = {
        "any": {"vegan", "vegetarian", "pescatarian", "meat"},
        "pescatarian": {"vegan", "vegetarian", "pescatarian"},
        "vegetarian": {"vegan", "vegetarian"},
        "vegan": {"vegan"},
    }[diet]
    now = season(date)
    fitting = [
        r
        for r in pool
        if set(r.get("diet", [])) & allowed and ({"all", now} & set(r.get("seasons", ["all"])))
    ]
    return pick(fitting or pool, f"recipes-{date.year}", index, count)


def exchange_rate(http: Http, base: str, quote: str) -> float | None:
    if base == quote:
        return 1.0
    try:
        data = http.get_json(
            "https://api.frankfurter.dev/v1/latest",
            {"base": base, "symbols": quote},
            ttl=12 * 3600,
        )
        return float(data["rates"][quote])
    except Exception:
        pass
    try:
        data = http.get_json(f"https://open.er-api.com/v6/latest/{base}", ttl=12 * 3600)
        return float(data["rates"][quote])
    except Exception:
        return None
